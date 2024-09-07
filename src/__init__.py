import logging
import re
import sys
from typing import Callable, Any
import mobase

if sys.version_info >= (3, 9):
    from builtins import list as List
    from builtins import tuple as Tuple
    from builtins import dict as Dict
else:
    from typing import List, Tuple, Dict

def has(obj: Any, attr: str) -> Any:
    if not obj:
        return None
    return getattr(obj, attr, lambda *args, **kwargs: None)

class Plugin:
    def __init__(self, priority, name) -> None:
        self.priority = priority
        self.name = name

        # add exceptions here:
        self.dict: Dict[str, List[str]] = {
            # 'mod1 regex': ['1st plugin substr', 'substr in 2nd', 'etc.'] ,
            # 'mod2 regex': ['substr in 1st', 'substr in 2nd', 'etc.']
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
            ['(:?hot|bug)[ ._-]?fix',
                r'\bfix\b',
                'patch',
                'add[ ._-]?on',
                'expansion',
                'expanded',
                'extension',
                'ext',
                'ng',
                'conversion'
                'fix'
                'remastered']
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
        isSupported = self._version >= mobase.VersionInfo(2, 4, 0)
        if not isSupported:
            self._log.error('PluginSync does not support MO2 versions older than 2.4.0')
        return isSupported

    # Basic info
    def name(self) -> str:
        return 'Sync Plugins'

    def author(self) -> str:
        return 'coldrifting'

    def description(self) -> str:
        return 'Syncs plugin load order with mod order'

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(2, 2, 1)

    def settings(self) -> List[mobase.PluginSetting]:
        return [
            mobase.PluginSetting('enabled', 'enable this plugin', True),
            mobase.PluginSetting('masters', 'Check missing masters', True)
        ]
    
    def isActive(self) -> bool:
        return bool(self._organizer.pluginSetting(self.name(), 'enabled'))

    # Display
    def displayName(self) -> str:
        return 'Sync Plugins'

    def tooltip(self) -> str:
        return 'Enables & sorts plugins to match mod load order'

    def icon(self) -> Any:
        if self._version >= mobase.VersionInfo(2, 5, 0):
            from PyQt6.QtGui import QIcon # type: ignore
        else:
            from PyQt5.QtGui import QIcon # type: ignore
        return QIcon()

    def selectimpl(self, impls: List[Tuple[mobase.VersionInfo, Any]]) -> Any:
        for version, impl in impls:
            if self._version >= version:
                return impl
        return None

    # Plugin Logic
    def display(self) -> None:
        isMaster = self.selectimpl([(mobase.VersionInfo(2, 5, 0),
                                     has(self._pluginList, 'isMasterFlagged')),
                                    (mobase.VersionInfo(2, 4, 0),
                                     has(self._pluginList, 'isMaster'))])
        feature = self.selectimpl([(mobase.VersionInfo(2, 5, 2),
                                    has(has(self._organizer, 'gameFeatures')(), 'gameFeature')),
                                   (mobase.VersionInfo(2, 4, 0),
                                    has(has(self._organizer, 'managedGame')(), 'feature'))])
        ACTIVE = self.selectimpl([(mobase.VersionInfo(2, 5, 0), mobase.PluginState.ACTIVE),
                                  (mobase.VersionInfo(2, 4, 0), 2)])
        INACTIVE = self.selectimpl([(mobase.VersionInfo(2, 5, 0), mobase.PluginState.INACTIVE),
                                    (mobase.VersionInfo(2, 4, 0), 1)])


        checkMasters = bool(self._organizer.pluginSetting(self.name(), 'masters'))      
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
        if checkMasters:
            allLowered = [x.lower() for x in allPlugins]

        # Set load order
        self._pluginList.setLoadOrder(allPlugins)

        # Scan through all plugins
        for plugin in allPlugins:
            # Get the masters of the current plugin
            pmasters = self._pluginList.masters(plugin)
            canEnable = True
            # Check if all masters are present
            if checkMasters:
                for pmaster in pmasters:
                    if pmaster.lower() not in allLowered:
                        self._log.warning(f'{pmaster} not present, disabling {plugin}')
                        canEnable = False
                        break
            # Set the plugin state accordingly
            if canEnable:
                self._pluginList.setState(plugin, ACTIVE)
            else:
                self._pluginList.setState(plugin, INACTIVE)

        # Update the plugin list to use the new load order
        feature(mobase.GamePlugins).writePluginLists(self._pluginList)

        # Refresh the UI
        self._organizer.refresh()

        self._log.info('Sync complete')


# Tell Mod Organizer to initialize the plugin
def createPlugin() -> mobase.IPlugin:
    return PluginSync()
