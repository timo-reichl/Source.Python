import os
import re
import glob
import importlib.machinery

from configobj import ConfigObj

from auth.paths import BACKEND_CONFIG_FILE
from auth.base import PermissionSource
from paths import SP_PACKAGES_PATH

from players.helpers import playerinfo_from_index, uniqueid_from_playerinfo


class PermissionBase(set):
    def __init__(self, name):
        super().__init__()
        self.parents = set()
        self.cache = set()
        self.name = name
        self.data = {}

    def __hash__(self):
        return hash(self.name)

    def add(self, *args, **kwargs):
        super().add(*args, **kwargs)
        self._refresh_cache()

    def remove(self, *args, **kwargs):
        super().remove(*args, **kwargs)
        self._refresh_cache()

    @staticmethod
    def _compile_permission(permission):
        return re.compile(permission.replace(".", "\\.").replace("*", "(.*)"))

    def _refresh_cache(self):
        self.cache.clear()
        for permission in self:
            self.cache.add(self._compile_permission(permission))

    def has(self, permission):
        for re_perm in self.cache:
            if re_perm.match(permission):
                return True
        for parent in self.parents:
            if parent.has_permission(permission):
                return True
        return False

    def list_permissions(self):
        perms = set()
        perms.update(self)
        for parent in self.parents:
            perms.update(parent.list_permissions())
        return perms

    def get_data(self, node):
        if node in self.data:
            return self.data[node]
        else:
            for parent in self.parents:
                data = parent.get_data(node)
                if data is not None:
                    return data

    def add_parent(self, parent):
        self.parents.add(auth_manager.groups[parent])
        auth_manager.groups[parent].children.add(self)

    def remove_parent(self, parent):
        self.parents.remove(auth_manager.groups[parent])
        auth_manager.groups[parent].children.remove(self)


class PermissionPlayer(PermissionBase):
    def __new__(cls, name):
        if name in auth_manager.players:
            return auth_manager.players[name]
        else:
            player = super().__new__(cls)
            auth_manager.players[name] = player
            return player


class PermissionGroup(PermissionBase):
    def __new__(cls, name):
        if name in auth_manager.groups:
            return auth_manager.groups[name]
        else:
            group = super().__new__(cls)
            auth_manager.groups[name] = group
            return group

    def __init__(self, name):
        super().__init__(name)
        self.children = set()


class PermissionDict(dict):
    def __init__(self, permission_type):
        super().__init__()
        self.permission_type = permission_type

    def __missing__(self, key):
        self[key] = self.permission_type(key)
        return self[key]


class AuthManager(object):
    def __init__(self):
        self.groups = PermissionDict(PermissionGroup)
        self.players = PermissionDict(PermissionPlayer)
        self.available_backends = []
        self.active_backend = None

    def load(self):
        self._find_available_backends()
        self._load_config()

    def load_backend(self, backend_name):
        for backend in self.available_backends:
            if backend.name.casefold() == backend_name.casefold():
                self.active_backend = backend
                self.groups.clear()
                self.players.clear()
                backend.load()
                return True
        return False

    def _find_available_backends(self):
        for backend in glob.glob(SP_PACKAGES_PATH.joinpath("auth", "backends/*.py")):
            name = "auth.backend." + os.path.splitext(os.path.basename(backend))[0]
            loader = importlib.machinery.SourceFileLoader(name, backend)
            module = loader.load_module(name)
            for var in module.__dict__.values():
                if isinstance(var, PermissionSource):
                    self.available_backends.append(var)
                    break

    def _load_config(self):
        config = ConfigObj()
        config["Config"] = {
            "PermissionBackend": "flatfile"
        }

        backends_config = {}
        for backend in self.available_backends:
            backends_config[backend.name] = backend.options

        config["backends"] = backends_config
        config.filename = BACKEND_CONFIG_FILE

        if os.path.exists(BACKEND_CONFIG_FILE):
            user_config = ConfigObj(BACKEND_CONFIG_FILE)
            config.merge(user_config)

        config.write()

        for backend in self.available_backends:
            backend.options = config["backends"][backend.name]

        self.load_backend(config["Config"]["PermissionBackend"])

    def get_player(self, index):
        return self.players[uniqueid_from_index(index)]

    def get_group(self, group_name):
        return self.groups[group_name]


def uniqueid_from_index(index):
    return uniqueid_from_playerinfo(playerinfo_from_index(index))

auth_manager = AuthManager()
