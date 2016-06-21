# -*- coding: utf-8 -*-
from gi.repository import Gtk, GLib, Gio

from threading import Thread
from uuid import uuid4
from traceback import print_exc
from os import stat

from formiko.vim import VimEditor
from formiko.sourceview import SourceView
from formiko.renderer import Renderer
from formiko.dialogs import QuitDialogWithoutSave, FileOpenDialog
from formiko.menu import AppMenu
from formiko.preferences import Preferences
from formiko.user import UserCache, UserPreferences

NOT_SAVED_NAME = 'Not saved document'


class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, editor, file_name=''):
        assert editor in ('vim', 'source', None)
        self.server_name = str(uuid4())
        self.runing = True
        self.editor_type = editor
        self.cache = UserCache()
        self.preferences = UserPreferences()
        super(AppWindow, self).__init__()
        self.actions()
        self.connect("delete-event", self.on_delete)
        headerbar = Gtk.HeaderBar()
        headerbar.set_show_close_button(True)
        self.fill_headerbar(headerbar)
        self.set_titlebar(headerbar)
        self.set_icon(self.render_icon(Gtk.STOCK_EDIT, Gtk.IconSize.DIALOG))
        self.layout(file_name)

        self.__last_changes = 0
        GLib.timeout_add(200, self.check_in_thread)

    def actions(self):
        action = Gio.SimpleAction.new("open-document", None)
        action.connect("activate", self.on_open_document)
        self.add_action(action)

        action = Gio.SimpleAction.new("save-document", None)
        action.connect("activate", self.on_save_document)
        action.set_enabled(False)
        self.add_action(action)

        action = Gio.SimpleAction.new("save-document-as", None)
        action.connect("activate", self.on_save_document_as)
        action.set_enabled(self.editor_type == 'source')
        self.add_action(action)

        action = Gio.SimpleAction.new("close-window", None)
        action.connect("activate", self.on_close_window)
        self.add_action(action)

        action = Gio.SimpleAction.new_stateful(
            "change-preview", GLib.VariantType.new('q'),
            GLib.Variant('q', self.preferences.preview))
        action.connect("activate", self.on_change_preview)
        self.add_action(action)

        action = Gio.SimpleAction.new_stateful(
            "change-writer", GLib.VariantType.new("s"),
            GLib.Variant('s', self.preferences.writer))
        action.connect("activate", self.on_change_writer)
        self.add_action(action)

        action = Gio.SimpleAction.new_stateful(
            "change-parser", GLib.VariantType.new('s'),
            GLib.Variant('s', self.preferences.parser))
        action.connect("activate", self.on_change_parser)
        self.add_action(action)

        action = Gio.SimpleAction.new_stateful(
            "custom-style-toggle", GLib.VariantType.new('b'),
            GLib.Variant('b', self.preferences.custom_style))
        action.connect("activate", self.on_custom_style_toggle)
        self.add_action(action)

        action = Gio.SimpleAction.new_stateful(
            "change-style", GLib.VariantType.new('s'),
            GLib.Variant('s', self.preferences.style))
        action.connect("activate", self.on_change_style)
        self.add_action(action)

        action = Gio.SimpleAction.new("reset-preferences", None)
        action.connect("activate", self.on_reset_preferences)
        self.add_action(action)

        action = Gio.SimpleAction.new("save-preferences", None)
        action.connect("activate", self.on_save_preferences)
        self.add_action(action)

    def on_close_window(self, action, *params):
        if self.ask_if_modified():
            self.save_win_state()
            self.destroy()

    def on_open_document(self, actions, *params):
        dialog = FileOpenDialog(self)
        dialog.add_filter_rst()
        dialog.add_filter_plain()
        dialog.add_filter_all()

        if dialog.run() == Gtk.ResponseType.ACCEPT:
            if self.editor_type == 'source' and \
                    self.get_title() == NOT_SAVED_NAME:
                self.editor.read_from_file(dialog.get_filename())
            else:
                self.get_application().new_window(self.editor_type,
                                                  dialog.get_filename())
        dialog.destroy()

    def on_save_document(self, action, *params):
        if self.editor_type == 'source':
            self.editor.save(self)

    def on_save_document_as(self, action, *params):
        if self.editor_type == 'source':
            self.editor.save_as(self)

    def on_delete(self, *args):
        rv = self.ask_if_modified()
        if rv:
            self.save_win_state()
        return not rv

    def on_change_preview(self, action, param):
        if not getattr(self, 'paned', False):
            return
        orientation = param.get_uint16()
        if self.paned.get_orientation() != orientation:
            self.paned.set_orientation(orientation)
            if orientation == Gtk.Orientation.HORIZONTAL:
                self.paned.set_position(self.paned.get_allocated_width()/2)
            else:
                self.paned.set_position(self.paned.get_allocated_height()/2)
            self.preferences.preview = orientation

    def on_change_parser(self, action, param):
        parser = param.get_string()
        if parser != self.renderer.get_parser():
            self.renderer.set_writer(parser)
            self.preferences.parser = parser

    def on_change_writer(self, action, param):
        writer = param.get_string()
        if writer != self.renderer.get_writer():
            self.renderer.set_writer(writer)
            self.preferences.writer = writer

    def on_custom_style_toggle(self, action, param):
        custom_style = not self.preferences.custom_style
        self.preferences.custom_style = custom_style
        if custom_style and self.preferences.style:
            self.renderer.set_style(self.preferences.style)
        else:
            self.renderer.set_style('')

    def on_change_style(self, action, param):
        style = param.get_string()
        self.preferences.style = style
        if self.preferences.custom_style and style:
            self.renderer.set_style(self.preferences.style)
        else:
            self.renderer.set_style('')

    def on_reset_preferences(self, action, param):
        self.pref_menu.reset()

    def on_save_preferences(self, action, param):
        self.preferences.save()

    def ask_if_modified(self):
        if self.editor_type:
            if self.editor.is_modified:
                dialog = QuitDialogWithoutSave(self,
                                               self.editor.file_name)
                if dialog.run() != Gtk.ResponseType.OK:
                    dialog.destroy()
                    return False        # fo not quit
            self.runing = False
            if self.editor_type == 'vim':
                self.editor.vim_quit()  # do call destroy_from_vim
        else:
            self.runing = False
        return True                     # do quit

    def destroy_from_vim(self, *args):
        self.runing = False
        self.destroy()

    def save_win_state(self):
        self.cache.width, self.cache.height = self.get_size()
        if getattr(self, 'paned', False):
            self.cache.paned = self.paned.get_position()
        self.cache.is_maximized = self.is_maximized()
        self.cache.save()

    def fill_headerbar(self, toolbar):
        btn = Gtk.Button(label="Open")
        btn.set_action_name("win.open-document")
        toolbar.pack_start(btn)

        self.pref_menu = Preferences()

        btn = Gtk.MenuButton(popover=self.pref_menu)
        icon = Gio.ThemedIcon(name="emblem-system-symbolic")
        btn.add(Gtk.Image.new_from_gicon(icon, Gtk.IconSize.BUTTON))
        btn.set_tooltip_text("Preferences")
        toolbar.pack_end(btn)

        btn = Gtk.MenuButton()
        btn.set_menu_model(AppMenu())
        icon = Gio.ThemedIcon(name="view-list-symbolic")
        btn.add(Gtk.Image.new_from_gicon(icon, Gtk.IconSize.BUTTON))
        btn.set_tooltip_text("Menu")
        toolbar.pack_end(btn)

        if self.editor_type == 'source':
            btn = Gtk.Button(label="Save")
            btn.set_action_name("win.save-document")
            toolbar.pack_end(btn)

    def fill_panned(self, file_name):
        if self.editor_type == 'vim':
            self.editor = VimEditor(self, self.server_name, file_name)
        else:
            self.editor = SourceView(file_name)
        self.paned.add1(self.editor)
        self.renderer = Renderer(self,
                                 parser=self.preferences.parser,
                                 writer=self.preferences.writer)
        if self.preferences.custom_style and self.preferences.style:
            self.renderer.set_style(self.preferences.style)
        self.paned.add2(self.renderer)

    def layout(self, file_name):
        self.set_default_size(self.cache.width, self.cache.height)
        box = Gtk.VBox()
        self.add(box)

        if self.editor_type:
            self.paned = Gtk.Paned(orientation=self.preferences.preview,
                                   position=self.cache.paned)
            box.pack_start(self.paned, True, True, 0)
            self.fill_panned(file_name)
        else:
            self.file_name = file_name
            self.set_title(file_name)
            self.renderer = Renderer(self,
                                     parser=self.preferences.parser,
                                     writer=self.preferences.writer)
            if self.preferences.custom_style and self.preferences.style:
                self.renderer.set_style(self.preferences.style)
            box.pack_start(self.renderer, True, True, 0)

        if self.cache.is_maximized:
            self.maximize()

    def check_in_thread(self):
        if self.runing:
            if self.editor_type == 'vim':
                thread = Thread(target=self.refresh_from_vim)
            elif self.editor_type == 'source':
                thread = Thread(target=self.refresh_from_source)
            else:   # self.editor = None
                thread = Thread(target=self.refresh_from_file)
            thread.start()

    def not_running(self):
        if not self.runing:
            raise SystemExit(0)

    def refresh_from_vim(self):
        another_file = False
        try:
            star = '*' if self.editor.is_modified else ''
            self.not_running()
            title = star + (self.editor.file_name or NOT_SAVED_NAME)
            if title != self.get_title():
                GLib.idle_add(self.set_title, title)
                another_file = True
            self.not_running()
            last_changes = self.editor.get_vim_changes()

            if last_changes > self.__last_changes or another_file:
                self.__last_changes = last_changes
                self.not_running()
                lines = self.editor.get_vim_lines()
                self.not_running()
                buff = self.editor.get_vim_get_buffer(lines)
                self.not_running()
                row, col = self.editor.get_vim_pos()
                pos = 0
                for i in range(row-1):
                    pos = buff.find('\n', pos)+1
                pos += col
                GLib.idle_add(self.renderer.render, buff, pos)
            GLib.timeout_add(300, self.check_in_thread)
        except SystemExit:
            return
        except:
            print_exc()

    def refresh_from_source(self):
        try:
            action = self.lookup_action("save-document")
            modified = self.editor.is_modified
            action.set_enabled(modified)

            star = '*' if modified else ''
            title = star + (self.editor.file_name or NOT_SAVED_NAME)
            if title != self.get_title():
                GLib.idle_add(self.set_title, title)

            last_changes = self.editor.changes
            if last_changes > self.__last_changes:
                self.__last_changes = last_changes
                GLib.idle_add(self.renderer.render,
                              self.editor.text, self.editor.position)
            GLib.timeout_add(100, self.check_in_thread)
        except:
            print_exc()

    def refresh_from_file(self):
        try:
            last_changes = stat(self.file_name).st_ctime
            if last_changes > self.__last_changes:
                self.__last_changes = last_changes
                with open(self.file_name) as source:
                    buff = source.read()
                    GLib.idle_add(self.renderer.render, buff)
        except:
            print_exc()
        GLib.timeout_add(500, self.check_in_thread)