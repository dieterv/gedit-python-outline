#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the Python Outline Plugin for Gedit
# Copyright (C) 2007 Dieter Verfaillie <dieterv@optionexplicit.be>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

from gi.repository import Gtk, GObject, Gedit, GdkPixbuf
try:
    from logilab.astng import builder
except ImportError:
    builder = None

DEBUG = False

def document_is_python(document):
    if not document:
        return False
    uri = str(document.get_uri_for_display())
    if document.get_mime_type() == 'text/x-python' or \
        uri.endswith('.py') or uri.endswith('.pyw'):
            return True
    return False


class OutlineBox(Gtk.Grid):
    def __init__(self):
        Gtk.Grid.__init__(self)
        self.orientation = Gtk.Orientation.VERTICAL

        scrolledwindow = Gtk.ScrolledWindow()
        scrolledwindow.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolledwindow.set_property('expand', True)

        self.treeview = treeview = Gtk.TreeView()
        treeview.set_rules_hint(True)
        treeview.set_headers_visible(False)
        treeview.set_enable_search(True)
        treeview.set_reorderable(False)
        treeselection = treeview.get_selection()
        treeselection.connect('changed', self.on_selection_changed)

        col = Gtk.TreeViewColumn('Name')
        col.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
        col.set_expand(True)

        # create renderer for the icon in each row
        render_pixbuf = Gtk.CellRendererPixbuf()
        render_pixbuf.set_property('xalign', 0.5)
        render_pixbuf.set_property('yalign', 0.5)
        render_pixbuf.set_property('xpad', 2)
        render_pixbuf.set_property('ypad', 2)
        col.pack_start(render_pixbuf, False)
        col.add_attribute(render_pixbuf, 'pixbuf', 0)

        # create renderer for the text in each row
        render_text = Gtk.CellRendererText()
        render_pixbuf.set_property('xalign', 0)
        render_pixbuf.set_property('yalign', 0.5)
        col.pack_start(render_text, True)
        col.add_attribute(render_text, 'text', 1)

        treeview.append_column(col)
        treeview.set_search_column(1)

        scrolledwindow.add(treeview)
        self.add(scrolledwindow)
        self.show_all()

    def on_selection_changed(self, selection):
        model, iter = selection.get_selected()
        if not iter:
            return
        line_no = model.get_value(iter, 3)
        if not line_no < 0:
            model._document.goto_line(line_no)
            model._view.scroll_to_cursor()


class OutlineModel(Gtk.TreeStore):
    moduleIcon = Gtk.Window().render_icon(Gtk.STOCK_COPY, Gtk.IconSize.MENU)
    importIcon = Gtk.Window().render_icon(Gtk.STOCK_JUMP_TO, Gtk.IconSize.MENU)
    classIcon = Gtk.Window().render_icon(Gtk.STOCK_FILE, Gtk.IconSize.MENU)
    functionIcon = Gtk.Window().render_icon(Gtk.STOCK_EXECUTE, Gtk.IconSize.MENU)
    attributeIcon = Gtk.Window().render_icon(Gtk.STOCK_COPY, Gtk.IconSize.MENU)
    errorIcon = Gtk.Window().render_icon(Gtk.STOCK_DIALOG_ERROR, Gtk.IconSize.MENU)

    def __init__(self, view, document):
        self._view = view
        self._document = document

        # icon, name, class_name, line_no, docstring
        Gtk.TreeStore.__init__(self, GdkPixbuf.Pixbuf, str, str, int, str)

        if not builder:
            self.append(None, [self.errorIcon, 'logilab.astng missing or invalid', None, -1, ''])
            return
        
        start, end = document.get_bounds()
        text = document.get_text(start, end, False)
        
        try:
            tree = builder.ASTNGBuilder().string_build(text)
        except Exception, e:
            self.append(None, [self.errorIcon, '%s: %s' % (e.__class__.__name__, e.msg), None, e.lineno-1, e.text])
            return

        for n in tree.body:
            self.append_member(n)

    def append_member(self, member, parent=None):
        classname = member.__class__.__name__
        lineno = member.lineno - 1 # document is zero indexed
        docstring = getattr(member, 'doc', '')

        if classname == 'From':
            for name, alias in member.names:
                if alias:
                    item = self.append(parent, [self.importIcon, '%s [%s] from %s' % (alias, name, member.modname), classname, lineno, docstring])
                else:
                    item = self.append(parent, [self.importIcon, '%s from %s' % (name, member.modname), classname, lineno, docstring])
        elif classname == 'Import':
            for name, alias in member.names:
                if alias:
                    item = self.append(parent, [self.importIcon, '%s [%s]' % (alias, name), classname, lineno, docstring])
                else:
                    item = self.append(parent, [self.importIcon, name, classname, lineno, docstring])
        elif classname == 'Function':
            item = self.append(parent, [self.functionIcon, member.name, classname, lineno, docstring])
        elif classname == 'Class':
            if getattr(member, 'basenames', None):
                item = self.append(parent, [self.classIcon, '%s (%s)' % (member.name, ', '.join(member.basenames)), classname, lineno, docstring])
            else:
                item = self.append(parent, [self.classIcon, member.name, classname, lineno, docstring])
        elif classname == 'Assign':
            for target in member.targets:
                self.append_member(target, parent=parent)
        elif classname == 'AssAttr':
            item = self.append(parent, [self.attributeIcon, member.attrname, classname, lineno, docstring])
        elif classname == 'AssName':
            item = self.append(parent, [self.attributeIcon, member.name, classname, lineno, docstring])
        else:
            if DEBUG:
                print 'ERROR: unknown', classname, 'object:', getattr(member, 'name', str(member)), 'on line', lineno
            return

        for m in getattr(member, 'body', []):
            self.append_member(m, parent=item)


class PythonOutlineInstance(object):
    _title = "Python Outline"
    _name = "PythonOutlinePanel"

    def __init__(self, plugin, window):
        self._window = window
        self._plugin = plugin
        # create the outline control
        self.outlinebox = OutlineBox()
        # add the outline control to the side panel tab
        self.panel = self._window.get_side_panel()
        self.panel.add_item(
            self.outlinebox, self._name, self._title, 
            Gtk.Image.new_from_stock(Gtk.STOCK_INDEX, Gtk.IconSize.MENU)
        )
        self.panel.activate_item(self.outlinebox)

    def deactivate(self):
        # remove the side panel tab that has our outline
        self.panel.remove_item(self.outlinebox)
        self._window = None
        self._plugin = None

    def update_treeview(self):
        model = OutlineModel(self._window.get_active_view(), self._window.get_active_document())
        self.outlinebox.treeview.set_model(model)


class PythonOutlinePlugin(GObject.Object, Gedit.WindowActivatable):
    __gtype_name__ = 'PythonOutline'
    window = GObject.property(type=Gedit.Window)

    def __init__(self):
        GObject.Object.__init__(self)
        self._instances = {}

    def do_activate(self):
        self._handlers = []
        self._handlers.append(
            self.window.connect('tab-removed', self.on_tab_removed))
        self._handlers.append(
            self.window.connect('active-tab-changed', self.on_active_tab_changed))
        self._handlers.append(
            self.window.connect('active-tab-state-changed', self.on_active_tab_state_changed))

    def do_deactivate(self):
        for handler_id in self._handlers[:]:
            self.window.disconnect(handler_id)
            self._handlers.remove(handler_id)

    def on_tab_removed(self, window, tab, data=None):
        if window not in self._instances.keys():
            return
        if not window.get_active_tab():
            self._instances[window].deactivate()
            del self._instances[window]

    def on_active_tab_changed(self, window, tab, data=None):
        self.update_outline(window)

    def on_active_tab_state_changed(self, window, data=None):
        self.update_outline(window)
            
    def update_outline(self, window):
        document = window.get_active_document()
        outline = self._instances.get(window)
        if not outline:
            if document_is_python(document):
                outline = self._instances[window] = PythonOutlineInstance(
                    self, window)
        elif not document_is_python(document):
            self._instances[window].deactivate()
            del self._instances[window]
            return None
        if outline:
            outline.update_treeview()
        return outline
