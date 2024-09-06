import mobase
import re
from typing import List, Callable
import logging
import sys

if sys.version_info >= (3, 9):
    Tuple = tuple
else:
    from typing import Tuple

class Plugin:
    def __init__(self, priority, name) -> None:
        self.priority = priority
        self.name = name

        # add exceptions here:
        self.dict = {
            # "mod1 regex": ["1st plugin substr", "substr in 2nd", "etc."] ,
            # "mod2 regex": ["substr in 1st", "substr in 2nd", "etc."]
        }

    def __lt__(self, other) -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority

        lc_a = self.name.lower()
        lc_b = other.name.lower()
        for (k, arr) in self.dict.items():
            if re.search(k, lc_a):
                for n in arr:
                    if n in lc_a:
                        return True
                    if n in lc_b:
                        return False

        # within a plugin there can be several esps. something that fixes stuff
        # should come last. if not enough use self.dict for the exceptions

        patts = \
            ["(:?hot|bug)[ ._-]?fix",
                r"\bfix\b",
                "patch",
                "add[ ._-]?on",
                "expansion",
                "expanded",
                "extension",
                "ext",
                "remastered"]
        for pattern in patts:
            if re.search(pattern, lc_a) != re.search(pattern, lc_b):
                return re.search(pattern, lc_a) is None

        # generally shorter should come first
        return len(lc_a) < len(lc_b) or self.name < other.name

class PluginSync(mobase.IPluginTool):

    _organizer: mobase.IOrganizer
    _modList: mobase.IModList
    _pluginList: mobase.IPluginList

    _version: mobase.VersionInfo

    def __init__(self) -> None:
        self._log = logging.getLogger(__name__)
        super().__init__()

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        self._modList = organizer.modList()
        self._pluginList = organizer.pluginList()

        self._version = self._organizer.appVersion()
        isSupported = self._version >= mobase.VersionInfo(2, 2, 2)
        if not isSupported:
            self._log.error('PluginSync does not support MO2 versions older than 2.5.0')
        return isSupported

    # Basic info
    def name(self) -> str:
        return "Sync Plugins"

    def author(self) -> str:
        return "coldrifting"

    def description(self) -> str:
        return "Syncs plugin load order with mod order"

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(2, 2, 0, mobase.ReleaseType.FINAL)

    def settings(self) -> List[mobase.PluginSetting]:
        return [
            mobase.PluginSetting("enabled", "enable this plugin", True)
        ]

    # Display
    def displayName(self) -> str:
        return "Sync Plugins"

    def tooltip(self) -> str:
        return "Applies plugins to match mod load order"

    def icon(self) -> any:
        if self._version >= mobase.VersionInfo(2, 5, 2):
            from PyQt6.QtGui import QIcon
        else:
            from PyQt5.QtGui import QIcon
        return QIcon()

    def selectimpl(self, impls: List[Tuple[mobase.VersionInfo, Callable]]) -> Callable:
        for version, impl in impls:
            if self._version >= version:
                return impl
        return None

    # Plugin Logic
    def display(self) -> bool:
        isMaster = self.selectimpl([(mobase.VersionInfo(2, 5, 0), getattr(self._pluginList, 'isMasterFlagged', None)), 
                                    (mobase.VersionInfo(2, 0, 0), getattr(self._pluginList, 'isMaster', None))])
        feature = self.selectimpl([(mobase.VersionInfo(2, 5, 2), getattr(self._organizer.gameFeatures(), 'gameFeature', None)),
                                   (mobase.VersionInfo(2, 0, 0), getattr(self._organizer.managedGame(), 'feature', None))])
        
        self._log.info('Sync started...')
        # Get all plugins as a list
        allPlugins = self._pluginList.pluginNames()

        # Sort the list by plugin origin
        allPlugins = sorted(
            allPlugins,
            key=lambda x: Plugin(self._modList.priority(self._pluginList.origin(x)), x)
        )

        # Split into two lists, master files and regular plugins
        plugins = []
        masters = []
        
        for plugin in allPlugins:
            if isMaster(plugin):
                masters.append(plugin)
            else:
                plugins.append(plugin)

        # Merge masters into the plugin list at the begining
        allPlugins = masters + plugins
        allLowered = [x.lower() for x in allPlugins]

        # Set load order
        self._pluginList.setLoadOrder(allPlugins)

        # Scan through all plugins
        for plugin in allPlugins:
            # Get the masters of the current plugin
            pmasters = self._pluginList.masters(plugin)
            canEnable = True
            # Check if all masters are present
            for pmaster in pmasters:
                if pmaster.lower() not in allLowered:
                    self._log.warn(f'{pmaster} not present, disabling {plugin}')
                    canEnable = False
                    break
            # Set the plugin state accordingly
            if canEnable:
                self._pluginList.setState(plugin, mobase.PluginState.ACTIVE)
            else:
                self._pluginList.setState(plugin, mobase.PluginState.INACTIVE)

        # Update the plugin list to use the new load order
        feature(mobase.GamePlugins).writePluginLists(self._pluginList)

        # Refresh the UI
        self._organizer.refresh()

        self._log.info('Sync complete')

        return True


# Tell Mod Organizer to initialize the plugin
def createPlugin() -> mobase.IPlugin:
    return PluginSync()
