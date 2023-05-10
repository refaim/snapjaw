import argparse
import enum
import functools
import glob
import json
import logging
import multiprocessing
import os
import shutil
import sys
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from tempfile import TemporaryDirectory
from typing import Optional

import colorama as cr
import humanize
import tabulate
from checksumdir import dirhash
from dataclasses_json import dataclass_json

import mygit
import toc


class CliError(RuntimeError):
    pass


@dataclass_json
@dataclass
class ConfigAddon:
    name: str
    url: str
    branch: str
    commit: str
    released_at: datetime
    installed_at: datetime
    checksum: Optional[str] = None


@dataclass_json
@dataclass
class Config:
    addons_by_key: dict[str, ConfigAddon]

    @staticmethod
    def load_or_setup(path: str):
        if os.path.exists(path):
            with open(path) as config_file:
                config = Config.from_json(config_file.read())
        else:
            config = Config(addons_by_key={})
        setattr(config, '_loaded_from', path)
        return config

    def save(self):
        sorted_addons_by_key = {}
        for k, v in sort_addons_dict(self.addons_by_key).items():
            sorted_addons_by_key[k] = v
        self.addons_by_key = sorted_addons_by_key
        with open(getattr(self, '_loaded_from'), 'w') as config_file:
            json.dump(json.loads(self.to_json()), config_file, indent=4)

    @staticmethod
    def addon_name_to_key(name: str) -> str:
        return name.lower()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cmd_args = parse_args()
    try:
        cmd_args.callback(cmd_args)
    except CliError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--addons-dir',
        required=False,
        type=arg_type_dir,
        default=os.path.join(os.getcwd(), 'Interface\\Addons'),
        help='optional path to Interface\\Addons directory')

    subparsers = parser.add_subparsers(required=True)

    install = subparsers.add_parser('install', help='install new addon(s)')
    install.add_argument('url', type=arg_type_git_repo_url, help='url to git repository')
    install.set_defaults(callback=functools.partial(run_command, cmd_install, False))

    update = subparsers.add_parser('remove', help='remove installed addon')
    update.add_argument('name', help='addon name')
    update.set_defaults(callback=functools.partial(run_command, cmd_remove, False))

    update = subparsers.add_parser('update', help='update installed addon(s)')
    update.add_argument('name', help='addon name', nargs='*')
    update.set_defaults(callback=functools.partial(run_command, cmd_update, False))

    status = subparsers.add_parser('status', help='list installed addons')
    status.add_argument('-v', '--verbose', action='store_true', help='enable more verbose output')
    status.set_defaults(callback=functools.partial(run_command, cmd_status, True))

    return parser.parse_args()


def arg_type_dir(value):
    if not os.path.isdir(value):
        raise argparse.ArgumentTypeError('invalid directory path')
    return value


def arg_type_git_repo_url(value):
    scheme, netloc, path, params, query, fragment = urllib.parse.urlparse(value)
    if netloc in ('github.com', 'gitlab.com'):
        if not path.endswith('.git'):
            path += '.git'
    else:
        raise argparse.ArgumentTypeError('invalid git repository url')
    return urllib.parse.urlunparse((scheme, netloc, path, params, query, fragment))


def run_command(cmd_callback, read_only, args):
    config_path = os.path.join(args.addons_dir, 'snapjaw.json')
    backup_path = os.path.join(args.addons_dir, 'snapjaw.backup.json')
    if not read_only and os.path.exists(config_path):
        shutil.copyfile(config_path, backup_path)

    config = Config.load_or_setup(config_path)
    try:
        cmd_callback(config, args)
        if not read_only:
            logging.info('Saving config...')
            config.save()
            logging.info('Done!')
    except Exception:
        if not read_only and os.path.exists(backup_path):
            shutil.copyfile(backup_path, config_path)
        raise


def cmd_install(config: Config, args):
    return install_addon(config, args.url, args.addons_dir)


def install_addon(config: Config, repo_url: str, addons_dir: str) -> None:
    logging.info(f'Cloning {repo_url}')

    with TemporaryDirectory() as repo_dir:
        try:
            repo = mygit.clone(repo_url, repo_dir)
        except mygit.GitError as error:
            raise CliError(str(error))

        try:
            addons_by_dir = {item.path: item for item in toc.find_addons(repo.workdir) if item.game_version <= 11200}
        except toc.ParseError as error:
            raise CliError(str(error))
        if not addons_by_dir:
            raise CliError('no vanilla addons found')

        for addon in addons_by_dir.values():
            logging.info(f'Installing addon "{addon.name}"')

            dst_addon_dir = os.path.join(addons_dir, addon.name)
            # TODO backup
            if os.path.exists(dst_addon_dir):
                remove_addon_dir(dst_addon_dir)

            shutil.copytree(addon.path, dst_addon_dir, ignore=shutil.ignore_patterns('.git*'))

            if repo.workdir != addon.path:
                # Copy additional readme files from root folder, if any
                for wc in ['*readme*', '*.txt', '*.html']:
                    for fn in glob.glob(wc, root_dir=repo.workdir):
                        src_path = os.path.join(repo.workdir, fn)
                        dst_path = os.path.join(dst_addon_dir, fn)
                        if not os.path.exists(dst_path):
                            shutil.copyfile(src_path, dst_path)

        config_addon = ConfigAddon(
            name=addon.name,
            url=repo_url,
            branch=repo.branch,
            commit=repo.head_commit_hex,
            released_at=repo.head_commit_time,
            installed_at=datetime.now(),
            checksum=dirhash(dst_addon_dir, 'sha1'))

        config.addons_by_key[addon_key(config_addon.name)] = config_addon
        config.save()

        logging.info('Done')


def cmd_remove(config: Config, args):
    addon = get_addon_from_config(config, args.name)
    del config.addons_by_key[addon_key(addon.name)]
    remove_addon_dir(os.path.join(args.addons_dir, args.name))


def remove_addon_dir(path):
    if os.path.islink(path):
        os.remove(path)
    elif os.path.isdir(path):
        try:
            shutil.rmtree(path)
        except OSError as e:
            if e.args and e.args[0] == 'Cannot call rmtree on a symbolic link':
                os.remove(path)
            else:
                raise
    else:
        assert False


def cmd_update(config: Config, args):
    if args.name:
        addons = [get_addon_from_config(config, name) for name in args.name]
    else:
        states = [state for state in get_addon_states(config, args.addons_dir) if state.status == AddonStatus.Outdated]
        addons = [config.addons_by_key[addon_key(state.addon)] for state in states]

    if not addons:
        print('No addons to update found')
        return

    for addon in addons:
        install_addon(config, addon.url, args.addons_dir)


def get_addon_from_config(config: Config, addon_name: str) -> ConfigAddon:
    addon = config.addons_by_key.get(addon_key(addon_name))
    if addon is None:
        raise argparse.ArgumentTypeError('unknown addon')
    return addon


def cmd_status(config: Config, args):
    addon_states = get_addon_states(config, args.addons_dir)
    if not addon_states:
        print('No addons found')
        return

    def format_dt(dt: Optional[datetime]) -> str:
        if not dt:
            return ''
        return humanize.naturaldate(dt)

    status_to_color = {
        AddonStatus.Missing: cr.Fore.RED,
        AddonStatus.Modified: cr.Fore.MAGENTA,
        AddonStatus.Outdated: cr.Fore.YELLOW,
        AddonStatus.Unknown: cr.Fore.YELLOW,
        AddonStatus.Untracked: cr.Fore.CYAN,
        AddonStatus.UpToDate: cr.Fore.GREEN,
    }

    table = []
    for state in addon_states:
        if args.verbose or state.status != AddonStatus.UpToDate:
            table.append([state.addon,
                          status_to_color[state.status] + state.status.value + cr.Fore.RESET,
                          format_dt(state.released_at),
                          format_dt(state.installed_at)])
    cr.init()
    # TODO add updated_at, rename released_at
    print(tabulate.tabulate(table, tablefmt='psql', headers=['addon', 'status', 'released_at', 'installed_at']))
    if not args.verbose:
        num_updated = Counter(s.status for s in addon_states)[AddonStatus.UpToDate]
        if num_updated > 0:
            msg = f'{num_updated}{" other" if table else ""} addons are up to date'
            print(cr.Fore.GREEN + msg + cr.Fore.RESET)
    cr.deinit()


class AddonStatus(enum.Enum):
    Unknown = 'unknown'
    Modified = 'modified'
    UpToDate = 'up-to-date'
    Outdated = 'outdated'
    Untracked = 'untracked'
    Missing = 'missing'


@dataclass
class AddonState:
    addon: str
    status: AddonStatus
    released_at: Optional[datetime] = None
    installed_at: Optional[datetime] = None


def get_addon_states(config: Config, addons_dir: str) -> list[AddonState]:
    url_to_branch_to_addons = {}
    for addon in config.addons_by_key.values():
        url_to_branch_to_addons.setdefault(addon.url, {}).setdefault(addon.branch, []).append(addon)

    addon_key_to_state = {}
    requests = [mygit.RemoteStateRequest(addon.url, addon.branch) for addon in config.addons_by_key.values()]
    for state in mygit.fetch_states(requests):
        for addon in url_to_branch_to_addons[state.url][state.branch]:
            if state.head_commit_hex is None:
                status = AddonStatus.Unknown
            elif dirhash(os.path.join(addons_dir, addon.name), 'sha1') != addon.checksum:
                status = AddonStatus.Modified
            elif state.head_commit_hex == addon.commit:
                status = AddonStatus.UpToDate
            else:
                status = AddonStatus.Outdated
            addon_key_to_state[addon_key(addon.name)] = AddonState(
                addon.name, status, addon.released_at, addon.installed_at)

    for name in os.listdir(addons_dir):
        path = os.path.join(addons_dir, name)
        name_key = addon_key(name)
        if os.path.isdir(path) and not name.startswith('Blizzard_') and name_key not in addon_key_to_state:
            addon_key_to_state[name_key] = AddonState(name, AddonStatus.Untracked, None, None)

    for name in set(config.addons_by_key.keys()) - set(addon_key_to_state.keys()):
        addon_key_to_state[addon_key(name)] = AddonState(name, AddonStatus.Missing, None, None)

    return list(sort_addons_dict(addon_key_to_state).values())


def sort_addons_dict(d: dict) -> dict:
    return {k: v for k, v in sorted(d.items(), key=lambda kv: (kv[0], kv[1]))}


def addon_key(name: str) -> str:
    return name.lower()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    sys.exit(main())
