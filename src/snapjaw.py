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
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

import colorama as cr
import humanize
import tabulate
from dataclasses_json import dataclass_json

import mygit
import signature
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
        self.addons_by_key = sort_addons_dict(self.addons_by_key)
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
        print(f'error: {error}', file=sys.stderr)
        return 1
    return 0


def parse_args():
    parser = argparse.ArgumentParser()

    wow_dir = None
    cwd = Path.cwd()
    while wow_dir is None and cwd != cwd.parent:
        if cwd.joinpath('WoW.exe').is_file():
            wow_dir = cwd
        cwd = cwd.parent

    addons_dir = None
    if wow_dir is not None:
        addons_dir = wow_dir.joinpath('Interface', 'Addons')

    parser.add_argument(
        '--addons-dir',
        required=False,
        type=arg_type_dir,
        default=addons_dir,
        help='optional path to Interface\\Addons directory')

    subparsers = parser.add_subparsers(required=True)

    install = subparsers.add_parser('install', help='install new addon(s)')
    install.add_argument('url', type=str, help='url to git repository')
    install.add_argument('--branch', type=str, help='specific git branch to use')
    install.set_defaults(callback=functools.partial(run_command, cmd_install, False))

    remove = subparsers.add_parser('remove', help='remove installed addon')
    remove.add_argument('names', help='addon name', nargs='+')
    remove.set_defaults(callback=functools.partial(run_command, cmd_remove, False))

    update = subparsers.add_parser('update', help='update installed addon(s)')
    update.add_argument('names', help='addon name', nargs='*')
    update.set_defaults(callback=functools.partial(run_command, cmd_update, False))

    status = subparsers.add_parser('status', help='list installed addons')
    status.add_argument('-v', '--verbose', action='store_true', help='enable more verbose output')
    status.set_defaults(callback=functools.partial(run_command, cmd_status, True))

    return parser.parse_args()


def arg_type_dir(value):
    if not os.path.isdir(value):
        raise argparse.ArgumentTypeError('invalid directory path')
    return value


# TODO get rid of read_only, check config.is_dirty()
def run_command(cmd_callback, read_only, args):
    if not os.path.isdir(args.addons_dir or ''):
        raise CliError('addons directory not found')

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
    scheme, netloc, path_string, params, query, fragment = urllib.parse.urlparse(args.url)

    branch_from_url = None
    if netloc in ('github.com', 'gitlab.com'):
        path = path_string.lstrip('/').split('/')
        author = path.pop(0)
        repository = path.pop(0)
        if path:
            if path[0] == '-' and path[1] == 'tree':
                path = path[2:]
            elif path[0] == 'tree':
                path = path[1:]
            branch_from_url = '/'.join(path)
        path_string = '/'.join([author, repository]) + '.git'

    if args.branch and branch_from_url and args.branch != branch_from_url:
        raise CliError(f'requested branch {args.branch}, but found branch {branch_from_url} in repository URL')

    repo_url = urllib.parse.urlunparse((scheme, netloc, path_string, params, query, fragment))
    return install_addon(config, repo_url, args.branch or branch_from_url, args.addons_dir)


def install_addon(config: Config, repo_url: str, branch: Optional[str], addons_dir: str) -> None:
    logging.info(f'Cloning {repo_url}')

    with TemporaryDirectory() as repo_dir:
        try:
            repo = mygit.clone(repo_url, branch, repo_dir)
        except mygit.GitError as error:
            raise CliError(str(error))

        try:
            addons_by_dir = {item.path: item for item in toc.find_addons(repo.workdir, 11200)}
        except toc.ParseError as error:
            raise CliError(str(error))
        if not addons_by_dir:
            raise CliError('no vanilla addons found')

        for addon in addons_by_dir.values():
            logging.info(f'Installing addon "{addon.name}", branch "{repo.branch}"')

            dst_addon_dir = os.path.join(addons_dir, addon.name)
            # TODO backup
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

            config.addons_by_key[addon_key(addon.name)] = ConfigAddon(
                name=addon.name,
                url=repo_url,
                branch=repo.branch,
                commit=repo.head_commit_hex,
                released_at=repo.head_commit_time,
                installed_at=datetime.now(),
                checksum=signature.calculate(dst_addon_dir))
            config.save()

        logging.info('Done')


def cmd_remove(config: Config, args):
    for name in args.names:
        key = addon_key(name)
        addon = config.addons_by_key.get(key)
        if addon is None:
            print(f'Addon not found: "{name}"')
        else:
            print(f'Removing addon {addon.name}')
            del config.addons_by_key[key]
            remove_addon_dir(os.path.join(args.addons_dir, addon.name))


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
        assert not os.path.exists(path)


def cmd_update(config: Config, args):
    if args.names:
        addons = [get_addon_from_config(config, name) for name in args.names]
    else:
        addons = []
        for state in get_addon_states(config, args.addons_dir):
            if state.error is not None:
                print(f'Error: {state.addon}: {state.error}')
            elif state.status == AddonStatus.Outdated:
                addons.append(config.addons_by_key[addon_key(state.addon)])

    if not addons:
        print('No addons to update found')
        return

    for addon in addons:
        install_addon(config, addon.url, addon.branch, args.addons_dir)


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
        AddonStatus.Error: cr.Fore.RED,
        AddonStatus.Missing: cr.Fore.RED,
        AddonStatus.Modified: cr.Fore.MAGENTA,
        AddonStatus.Outdated: cr.Fore.YELLOW,
        AddonStatus.Unknown: cr.Fore.YELLOW,
        AddonStatus.Untracked: cr.Fore.CYAN,
        AddonStatus.UpToDate: cr.Fore.GREEN,
    }

    has_error = any(state.error is not None for state in addon_states)

    table = []
    for state in addon_states:
        if args.verbose or state.status != AddonStatus.UpToDate:
            columns = [
                state.addon,
                status_to_color[state.status] + state.status.value + cr.Fore.RESET,
                format_dt(state.released_at),
                format_dt(state.installed_at),
            ]
            if has_error:
                columns.append(state.error or '')
            table.append(columns)

    # TODO add updated_at, rename released_at
    headers = ['addon', 'status', 'released_at', 'installed_at']
    if has_error:
        headers.append('error')

    cr.init()
    print(tabulate.tabulate(table, tablefmt='psql', headers=headers))
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
    Error = 'error'


@dataclass
class AddonState:
    addon: str
    status: AddonStatus
    error: Optional[str]
    released_at: Optional[datetime]
    installed_at: Optional[datetime]


def get_addon_states(config: Config, addons_dir: str) -> list[AddonState]:
    url_to_branch_to_addons = {}
    for addon in config.addons_by_key.values():
        url_to_branch_to_addons.setdefault(addon.url, {}).setdefault(addon.branch, []).append(addon)

    addon_key_to_state = {}
    requests = [mygit.RemoteStateRequest(addon.url, addon.branch) for addon in config.addons_by_key.values()]
    for state in mygit.fetch_states(requests):
        for addon in url_to_branch_to_addons[state.url][state.branch]:
            comment = None
            if state.error is not None:
                status = AddonStatus.Error
                comment = state.error
            elif state.head_commit_hex is None:
                status = AddonStatus.Unknown
            elif not signature.validate(os.path.join(addons_dir, addon.name), addon.checksum):
                status = AddonStatus.Modified
            elif state.head_commit_hex == addon.commit:
                status = AddonStatus.UpToDate
            else:
                status = AddonStatus.Outdated
            addon_key_to_state[addon_key(addon.name)] = AddonState(
                addon.name, status, comment, addon.released_at, addon.installed_at)

    for name in os.listdir(addons_dir):
        path = os.path.join(addons_dir, name)
        name_key = addon_key(name)
        if os.path.isdir(path) and not name.startswith('Blizzard_') and name_key not in addon_key_to_state:
            addon_key_to_state[name_key] = AddonState(name, AddonStatus.Untracked, None, None, None)

    for name in set(config.addons_by_key.keys()) - set(addon_key_to_state.keys()):
        addon_key_to_state[addon_key(name)] = AddonState(name, AddonStatus.Missing, None, None, None)

    return list(sort_addons_dict(addon_key_to_state).values())


def sort_addons_dict(d: dict) -> dict:
    return {k: v for k, v in sorted(d.items(), key=lambda kv: (kv[0], kv[1]))}


def addon_key(name: str) -> str:
    return name.lower()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    sys.exit(main())
