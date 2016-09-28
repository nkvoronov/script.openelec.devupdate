import threading

import xbmcgui
import requests

from . import addon, builds, utils, log, history, funcs
from .addon import L10n


class BaseInfoDialog(xbmcgui.WindowXMLDialog):
    def onAction(self, action):
        action_id = action.getId()
        if action_id in (xbmcgui.ACTION_SHOW_INFO,
                         xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.close()


class InfoDialog(BaseInfoDialog):
    def __new__(cls, *args):
        return super(InfoDialog, cls).__new__(
            cls, "script-devupdate-info.xml", addon.src_path)

    def __init__(self, vtitle, vtext):
        self.Title = vtitle
        self.Text = vtext

    def onInit(self):
        self.getControl(1).setLabel(self.Title)
        self.getControl(2).setText(self.Text)


class HistoryDialog(BaseInfoDialog):
    def __new__(cls, *args):
        return super(HistoryDialog, cls).__new__(
            cls, "script-devupdate-history.xml", addon.src_path)

    def __init__(self, vhistory):
        self.History = vhistory

    def onInit(self):
        if self.History is not None:
            self.getControl(1).setLabel(L10n(32031))
            install_list = self.getControl(2)
            for install in reversed(self.History):
                li = xbmcgui.ListItem()
                for attr in ('source', 'version'):
                    li.setProperty(attr, str(getattr(install, attr)))
                li.setProperty('timestamp', install.timestamp.strftime("%Y-%m-%d %H:%M"))
                install_list.addItem(li)
        else:
            self.getControl(1).setLabel(L10n(32032))


class BuildSelectDialog(xbmcgui.WindowXMLDialog):
    LABEL_ID = 100
    BUILD_LIST_ID = 20
    SOURCE_LIST_ID = 10
    INFO_TEXTBOX_ID = 200
    SETTINGS_BUTTON_ID = 30
    HISTORY_BUTTON_ID = 40
    CANCEL_BUTTON_ID = 50

    def __new__(cls, *args):
        return super(BuildSelectDialog, cls).__new__(
            cls, "script-devupdate-main.xml", addon.src_path)

    def __init__(self, vinstalled_build):
        self.Builds_focused = False
        self.Installed_build = vinstalled_build

        self.Sources = builds.sources()
        utils.add_custom_sources(self.Sources)

        self.Initial_source = addon.get_setting('source_name')
        try:
            self.Build_url = self.Sources[self.Initial_source]
        except KeyError:
            self.Build_url = self.Sources.itervalues().next()
            self.Initial_source = self.Sources.iterkeys().next()
        self.Builds = self.Get_build_links(self.Build_url)

        self.Build_infos = {}

    def __nonzero__(self):
        return self.Selected_build is not None

    def onInit(self):
        self.Selected_build = None

        self.Sources_list = self.getControl(self.SOURCE_LIST_ID)
        self.Sources_list.addItems(self.Sources.keys())

        self.Build_list = self.getControl(self.BUILD_LIST_ID)

        self.getControl(self.LABEL_ID).setLabel(builds.arch)

        self.Info_textbox = self.getControl(self.INFO_TEXTBOX_ID)

        if self.Builds:
            self.Selected_source_position = self.Sources.keys().index(self.Initial_source)

            self.Set_builds(self.Builds)
        else:
            self.Selected_source_position = 0
            self.Initial_source = self.Sources.iterkeys().next()
            self.setFocusId(self.SOURCE_LIST_ID)

        self.Selected_source = self.Initial_source

        self.Sources_list.selectItem(self.Selected_source_position)

        item = self.Sources_list.getListItem(self.Selected_source_position)
        self.Selected_source_item = item
        self.Selected_source_item.setLabel2('selected')

        self.Cancel_button = self.getControl(self.CANCEL_BUTTON_ID)
        self.Cancel_button.setVisible(bool(funcs.update_files()))

        threading.Thread(target=self.Get_and_set_build_info,
                         args=(self.Build_url,)).start()

    @property
    def selected_build(self):
        return self.Selected_build

    @property
    def selected_source(self):
        return self.Selected_source

    def onClick(self, controlID):
        if controlID == self.BUILD_LIST_ID:
            self.Selected_build = self.Builds[self.Build_list.getSelectedPosition()]
            self.close()
        elif controlID == self.SOURCE_LIST_ID:
            self.Build_url = self.Get_build_url()
            build_links = self.Get_build_links(self.Build_url)

            if build_links:
                self.Selected_source_item.setLabel2('')
                self.Selected_source_item = self.Sources_list.getSelectedItem()
                self.Selected_source_position = self.Sources_list.getSelectedPosition()
                self.Selected_source_item.setLabel2('selected')
                self.Selected_source = self.Selected_source_item.getLabel()

                self.Set_builds(build_links)

                threading.Thread(target=self.Get_and_set_build_info,
                                 args=(self.Build_url,)).start()

                self.Get_and_set_build_info(self.Build_url)
            else:
                self.Sources_list.selectItem(self.Selected_source_position)
        elif controlID == self.SETTINGS_BUTTON_ID:
            self.close()
            addon.open_settings()
        elif controlID == self.HISTORY_BUTTON_ID:
            dialog = HistoryDialog(history.get_full_install_history())
            dialog.doModal()
        elif controlID == self.CANCEL_BUTTON_ID:
            if utils.remove_update_files():
                utils.notify(L10n(32034))
                self.Cancel_button.setVisible(False)
                funcs.remove_notify_file()
                self.Info_textbox.setText("")

    def onAction(self, action):
        action_id = action.getId()
        if action_id in (xbmcgui.ACTION_MOVE_DOWN, xbmcgui.ACTION_MOVE_UP,
                         xbmcgui.ACTION_PAGE_DOWN, xbmcgui.ACTION_PAGE_UP,
                         xbmcgui.ACTION_MOUSE_MOVE):
            self.Set_build_info()

        elif action_id == xbmcgui.ACTION_SHOW_INFO:
            build_version = self.Build_list.getSelectedItem().getLabel()
            try:
                info = self.Build_infos[build_version]
            except KeyError:
                log.log("Build details for build {} not found".format(build_version))
            else:
                if info.details is not None:
                    try:
                        details = info.details.get_text()
                    except Exception as e:
                        log.log("Unable to retrieve build details: {}".format(e))
                    else:
                        if details:
                            build = "[B]{}[/B]\n\n".format(L10n(32035)).format(build_version)
                            dialog = InfoDialog(build, details)
                            dialog.doModal()

        elif action_id in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.close()

    def onFocus(self, controlID):
        if controlID != self.BUILD_LIST_ID:
            self.Info_textbox.setText("")
            self.Builds_focused = False

        if controlID == self.BUILD_LIST_ID:
            self.Builds_focused = True
            self.Set_build_info()
        elif controlID == self.SOURCE_LIST_ID:
            self.Info_textbox.setText("[COLOR=white]{}[/COLOR]".format(L10n(32141)))
        elif controlID == self.SETTINGS_BUTTON_ID:
            self.Info_textbox.setText("[COLOR=white]{}[/COLOR]".format(L10n(32036)))
        elif controlID == self.HISTORY_BUTTON_ID:
            self.Info_textbox.setText("[COLOR=white]{}[/COLOR]".format(L10n(32037)))
        elif controlID == self.CANCEL_BUTTON_ID:
            self.Info_textbox.setText("[COLOR=white]{}[/COLOR]".format(L10n(32038)))

    @utils.showbusy
    def Get_build_links(self, vbuild_url):
        links = []
        try:
            links = vbuild_url.builds()
        except requests.ConnectionError as e:
            utils.connection_error(str(e))
        except builds.BuildURLError as e:
            utils.bad_url(vbuild_url.url, str(e))
        except requests.RequestException as e:
            utils.url_error(vbuild_url.url, str(e))
        else:
            if not links:
                utils.bad_url(vbuild_url.url, L10n(32039).format(builds.arch))
        return links

    def Get_build_infos(self, vbuild_url):
        log.log("Retrieving build information")
        info = {}
        for info_extractor in vbuild_url.info_extractors:
            try:
                info.update(info_extractor.get_info())
            except Exception as e:
                log.log("Unable to retrieve build info: {}".format(str(e)))
        return info

    def Set_build_info(self):
        if self.Builds_focused:
            selected_item = self.Build_list.getSelectedItem()
            try:
                build_version = selected_item.getLabel()
            except AttributeError:
                log.log("Unable to get selected build name")
            else:
                try:
                    info = self.Build_infos[build_version].summary
                except KeyError:
                    info = ""
                    log.log("Build info for build {} not found".format(build_version))
                else:
                    log.log("Info for build {}:\n\t{}".format(build_version, info))
            self.Info_textbox.setText(info)

    def Get_and_set_build_info(self, vbuild_url):
        log.log("Build url {}".format(vbuild_url))
        self.Build_infos = self.Get_build_infos(vbuild_url)
        self.Set_build_info()

    def Get_build_url(self):
        source = self.Sources_list.getSelectedItem().getLabel()
        build_url = self.Sources[source]

        log.log("Full URL = " + build_url.url)
        return build_url

    def Set_builds(self, vbuilds):
        self.Builds = vbuilds
        self.Build_list.reset()
        for build in vbuilds:
            li = xbmcgui.ListItem()
            li.setLabel(build.version)
            li.setLabel2(build.date)
            if build > self.Installed_build:
                icon = 'upgrade'
            elif build < self.Installed_build:
                icon = 'downgrade'
            else:
                icon = 'installed'
            li.setIconImage("{}.png".format(icon))
            self.Build_list.addItem(li)
        self.setFocusId(self.BUILD_LIST_ID)
        self.Builds_focused = True
