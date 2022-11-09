import argparse
import contextlib
import functools
import glob
import json
import logging
import math
import os
import re
import shutil
import sys
import tempfile
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Generator, Optional

import colorama as cr
import git
import humanize
import tabulate
from checksumdir import dirhash
from dataclasses_json import dataclass_json


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


@dataclass(init=False)
class AddonInfo:
    name: str
    src_dir: str


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cmd_args = parse_args()
    cmd_args.callback(cmd_args)
    return 0


def parse_args():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)

    # TODO guess automatically by cwd
    parser.add_argument('--addons-dir', required=True, type=arg_type_dir)

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
    with clone_git_repo(repo_url) as repo:
        repo: git.Repo

        addons = find_addons(repo.working_dir, 11200)
        if not addons:
            raise ValueError('no addons found')
        for addon in addons:
            logging.info(f'Installing addon "{addon.name}"')
            dst_addon_dir = os.path.join(addons_dir, addon.name)
            if os.path.exists(dst_addon_dir):
                # TODO backup
                # TODO compare versions
                shutil.rmtree(dst_addon_dir)

            shutil.copytree(addon.src_dir, dst_addon_dir, ignore=shutil.ignore_patterns('.git*'))

            if repo.working_dir != addon.src_dir:
                # Copy additional readme files from root folder, if any
                for wc in ['*readme*', '*.txt', '*.html']:
                    for fn in glob.glob(wc, root_dir=repo.working_dir):
                        src_path = os.path.join(repo.working_dir, fn)
                        dst_path = os.path.join(dst_addon_dir, fn)
                        if not os.path.exists(dst_path):
                            shutil.copyfile(src_path, dst_path)

            commit = repo.head.commit
            config_addon = ConfigAddon(
                name=addon.name,
                url=repo.remotes[0].url,
                branch=repo.active_branch.name,
                commit=commit.hexsha,
                released_at=datetime.fromtimestamp(commit.committed_date),
                installed_at=datetime.now(),
                checksum=dirhash(dst_addon_dir, 'sha1'))

            config.addons_by_key[Config.addon_name_to_key(config_addon.name)] = config_addon
            config.save()

            logging.info('Done')


def cmd_remove(config: Config, args):
    addon = get_addon_from_config(config, args.name)
    del config.addons_by_key[Config.addon_name_to_key(addon.name)]
    addon_path = os.path.join(args.addons_dir, args.name)
    if os.path.exists(addon_path):
        shutil.rmtree(addon_path)


def cmd_update(config: Config, args):
    if args.name:
        addons = [get_addon_from_config(config, name) for name in args.name]
    else:
        addons = config.addons_by_key.values()
    for addon in addons:
        # TODO update only outdated addons
        install_addon(config, addon.url, args.addons_dir)


def get_addon_from_config(config: Config, addon_name: str) -> ConfigAddon:
    addon_key = Config.addon_name_to_key(addon_name)
    addon = config.addons_by_key.get(addon_key)
    if addon is None:
        raise argparse.ArgumentTypeError('unknown addon')
    return addon


def cmd_status(config: Config, args):
    @dataclass
    class GitRepoState:
        url: str
        branch: str
        head_commit_hash: Optional[str]

    ref_to_addons = {}
    for addon in config.addons_by_key.values():
        ref_to_addons.setdefault((addon.url, addon.branch), []).append(addon)

    # TODO handle exceptions
    def request_repo_state(state: GitRepoState) -> GitRepoState:
        upstream_hash = None
        # https://git-scm.com/docs/git-ls-remote.html
        for line in git.cmd.Git().ls_remote('--refs', '--heads', state.url).splitlines():
            ref_hash, ref = line.split()
            if ref.endswith('/' + state.branch):
                upstream_hash = ref_hash
        state.head_commit_hash = upstream_hash
        return state

    repo_states = [GitRepoState(repo_url, repo_branch, None) for repo_url, repo_branch in ref_to_addons.keys()]
    executor = ThreadPoolExecutor()
    futures = [executor.submit(request_repo_state, state) for state in repo_states]
    for i, future in enumerate(as_completed(futures)):
        future.result()
        print(f'{i + 1}/{len(repo_states)}', end='\r')

    @dataclass
    class AddonState:
        name: str
        status: str
        released_at: Optional[datetime] = None
        installed_at: Optional[datetime] = None

    n2k = Config.addon_name_to_key

    addon_key_to_state = {}
    for repo_state in repo_states:
        for addon in ref_to_addons[(repo_state.url, repo_state.branch)]:
            if repo_state.head_commit_hash is None:
                status = 'unknown'
            elif dirhash(os.path.join(args.addons_dir, addon.name), 'sha1') != addon.checksum:
                status = 'modified'
            elif repo_state.head_commit_hash == addon.commit:
                status = 'up-to-date'
            else:
                status = 'outdated'
            addon_key_to_state[n2k(addon.name)] = AddonState(addon.name, status, addon.released_at, addon.installed_at)

    for name in os.listdir(args.addons_dir):
        path = os.path.join(args.addons_dir, name)
        name_key = n2k(name)
        if os.path.isdir(path) and not name.startswith('Blizzard_') and name_key not in addon_key_to_state:
            addon_key_to_state[name_key] = AddonState(name, 'untracked', None, None)

    for name in set(config.addons_by_key.keys()) - set(addon_key_to_state.keys()):
        name_key = n2k(name)
        addon_key_to_state[name_key] = AddonState(name, 'folder-missing', None, None)

    if not addon_key_to_state:
        print('No addons found')
        return

    def format_dt(dt: Optional[datetime]) -> str:
        if not dt:
            return ''
        return humanize.naturaldate(dt)

    table = []
    for state in sort_addons_dict(addon_key_to_state).values():
        color = {
            'folder-missing': cr.Fore.RED,
            'modified': cr.Fore.MAGENTA,
            'outdated': cr.Fore.YELLOW,
            'unknown': cr.Fore.YELLOW,
            'untracked': cr.Fore.CYAN,
            'up-to-date': cr.Fore.GREEN,
        }[state.status]
        if args.verbose or state.status != 'up-to-date':
            table.append([state.name,
                          color + state.status + cr.Fore.RESET,
                          format_dt(state.released_at),
                          format_dt(state.installed_at)])
    cr.init()
    print(tabulate.tabulate(table, tablefmt='psql', headers=['addon', 'status', 'released_at', 'installed_at']))
    if not args.verbose:
        num_updated = Counter(s.status for s in addon_key_to_state.values())['up-to-date']
        if num_updated > 0:
            msg = f'{num_updated}{" other" if table else ""} addons are up to date'
            print(cr.Fore.GREEN + msg + cr.Fore.RESET)
    cr.deinit()


@contextmanager
def clone_git_repo(url: str) -> Generator[git.Repo, None, None]:
    with contextlib.ExitStack() as stack:
        repo_dir = stack.enter_context(tempfile.TemporaryDirectory())
        yield stack.enter_context(git.Repo.clone_from(url,
                                                      repo_dir,
                                                      progress=get_git_progress_callback(),
                                                      multi_options=['--depth 1']))


def get_git_progress_callback():
    prev_progress_len = [0]

    def progress(op_code, cur_count, max_count, message):
        output = f'{math.ceil(cur_count / max_count * 100)}%'
        if message:
            output = f'{output}, {message}'
        print(output.ljust(prev_progress_len[0], ' '), end='\r')
        prev_progress_len[0] = len(output) + 1
    
    return progress


def find_addons(directory, game_version) -> list[AddonInfo]:
    addons_by_subdir = {}
    for addon_dir, toc_path in find_toc_files(directory):
        match = re.search(r'## Interface:\s+(?P<v>\d+)', read_file(toc_path))
        if not match:
            assert False # TODO raise proper error
        addon_game_version = int(match.groupdict()['v'])
        if addon_game_version <= game_version:
            addon = AddonInfo()
            addon.name = os.path.splitext(os.path.basename(toc_path))[0]
            addon.src_dir = addon_dir
            if addon.src_dir in addons_by_subdir:
                assert False # TODO raise proper error
            addons_by_subdir[addon.src_dir] = addon
    return addons_by_subdir.values()


def read_file(path: str) -> str:
    for encoding in ['utf-8', None]:
        with open(path, encoding=encoding) as fp:
            try:
                return fp.read()
            except UnicodeDecodeError:
                pass
    raise ValueError(f'Unable to guess encoding of {path}')


def sort_addons_dict(d: dict) -> dict:
    return {k: v for k, v in sorted(d.items(), key=lambda kv: (kv[0], kv[1]))}


def find_toc_files(directory) -> Generator[tuple[str, str], None, None]:
    for folder, subfolders, files in os.walk(directory):
        for filename in files:
            if os.path.splitext(filename.lower())[1] == '.toc':
                yield folder, os.path.join(folder, filename)


if __name__ == '__main__':
    sys.exit(main())
