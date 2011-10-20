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


import os

import gtk
import gedit

import compiler
import gc
import glob
import time


class TreeModelASTVisitor(compiler.visitor.ASTVisitor):
    defaulticon = None

    moduleicon = gtk.Window().render_icon(gtk.STOCK_COPY, gtk.ICON_SIZE_MENU)
    importicon = gtk.Window().render_icon(gtk.STOCK_JUMP_TO, gtk.ICON_SIZE_MENU)
    classicon = gtk.Window().render_icon(gtk.STOCK_FILE, gtk.ICON_SIZE_MENU)
    functionicon = gtk.Window().render_icon(gtk.STOCK_EXECUTE, gtk.ICON_SIZE_MENU)

    def __init__(self, treemodel):
        compiler.visitor.ASTVisitor.__init__(self)

        self.treemodel = treemodel

    def walkChildren(self, node, parent=None):
        for child in node.getChildNodes():
            child.parent = node
            self.dispatch(child, parent)

    def default(self, node, parent=None):
        self.walkChildren(node, parent)


class OutlineTreeModelASTVisitor(TreeModelASTVisitor):
    def __init__(self, treemodel):
        TreeModelASTVisitor.__init__(self, treemodel)

    def visitAssAttr(self, node, parent=None):
        if hasattr(node.expr, 'name'):
            if node.expr.name == 'self':
                iter = self.treemodel.append(parent, (self.defaulticon, 'self.' + node.attrname, node.__class__.__name__, node.lineno, None))

    def visitAssName(self, node, parent=None):
        if hasattr(node.parent, 'parent'):
            if not hasattr(node.parent.parent, 'parent'):
                iter = self.treemodel.append(parent, (self.defaulticon, node.name, node.__class__.__name__, node.lineno, None))

    def visitClass(self, node, parent=None):
        iter = self.treemodel.append(parent, (self.classicon, node.name, node.__class__.__name__, node.lineno, node.doc))
        self.walkChildren(node.code, iter)

    def visitDecorators(self, node, parent=None):
        iter = self.treemodel.append(parent, (self.defaulticon, None, node.__class__.__name__, node.lineno, None))
        self.walkChildren(node, iter)

    def visitFrom(self, node, parent=None):
        for name in node.names:
            if name[1] is None:
                self.treemodel.append(parent, (self.importicon, name[0] + ' (' + node.modname + ')', node.__class__.__name__, node.lineno, None))
            else:
                self.treemodel.append(parent, (self.importicon, name[1] + ' = ' + name[0] + ' (' + node.modname + ')', node.__class__.__name__, node.lineno, None))

    def visitFunction(self, node, parent=None):
        iter = self.treemodel.append(parent, (self.functionicon, node.name, node.__class__.__name__, node.lineno, node.doc))
        self.walkChildren(node, iter)

    def visitImport(self, node, parent=None):
        for name in node.names:
            if name[1] is None:
                self.treemodel.append(parent, (self.importicon, name[0], node.__class__.__name__, node.lineno, None))
            else:
                self.treemodel.append(parent, (self.importicon, name[1] + ' = ' + name[0], node.__class__.__name__, node.lineno, None))

    def visitName(self, node, parent=None):
        if node.parent.__class__.__name__ in ['Class', 'Function']:
            self.treemodel.append(parent, (self.defaulticon, node.name, node.__class__.__name__, node.lineno, None))


class OutlineBox(gtk.VBox):
    def __init__(self):
        gtk.VBox.__init__(self)

        scrolledwindow = gtk.ScrolledWindow()
        scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        scrolledwindow.show()
        self.pack_start(scrolledwindow, True, True, 0)

        self.treeview = gtk.TreeView()
        self.treeview.set_rules_hint(True)
        self.treeview.set_headers_visible(False)
        self.treeview.set_enable_search(True)
        self.treeview.set_reorderable(False)
        self.treeselection = self.treeview.get_selection()
        self.treeselection.connect('changed', self.on_selection_changed)
        scrolledwindow.add(self.treeview)

        col = gtk.TreeViewColumn()
        col.set_title('name')
        col.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        col.set_expand(True)
        render_pixbuf = gtk.CellRendererPixbuf()
        render_pixbuf.set_property('xalign', 0.5)
        render_pixbuf.set_property('yalign', 0.5)
        render_pixbuf.set_property('xpad', 2)
        render_pixbuf.set_property('ypad', 2)
        col.pack_start(render_pixbuf, expand=False)
        col.add_attribute(render_pixbuf, 'pixbuf', 0)
        render_text = gtk.CellRendererText()
        render_text.set_property('xalign', 0)
        render_text.set_property('yalign', 0.5)
        col.pack_start(render_text, expand=True)
        col.add_attribute(render_text, 'text', 1)
        self.treeview.append_column(col)
        self.treeview.set_search_column(1)

        self.label = gtk.Label()
        self.pack_end(self.label, False)

        self.expand_classes = False
        self.expand_functions = False

        self.show_all()

    def on_toggle_expand_classes(self, action):
        self.expand_classes = action.get_active()

    def on_toggle_expand_functions(self, action):
        self.expand_functions = action.get_active()

    def on_row_has_child_toggled(self, treemodel, path, iter):
        if self.expand_classes and treemodel.get_value(iter, 2) == 'Class':
            self.treeview.expand_row(path, False)
        elif self.expand_functions and treemodel.get_value(iter, 2) == 'Function':
            self.treeview.expand_row(path, False)

    def on_selection_changed(self, selection):
        model, iter = selection.get_selected()
        if iter:
            lineno = model.get_value(iter, 3)
            if lineno:
                lineno = int(lineno) -1
                linestartiter = self.buffer.get_iter_at_line(lineno)
                lineenditer = self.buffer.get_iter_at_line(lineno)
                lineenditer.forward_line()
                line = self.buffer.get_text(linestartiter, lineenditer)
                name = model.get_value(iter, 1)
                start = line.find(name)
                if start > -1:
                    end = start + len(name)
                    self.buffer.select_range(
                        self.buffer.get_iter_at_line_offset(lineno, start),
                        self.buffer.get_iter_at_line_offset(lineno, end))
                    self.view.scroll_to_cursor()
                else:
                    #Todo: scroll view to lineno
                    pass

    def create_treemodel(self):
        treemodel = gtk.TreeStore(gtk.gdk.Pixbuf, str, str, str, str)
        handler = treemodel.connect('row-has-child-toggled', self.on_row_has_child_toggled)
        return treemodel, handler

    def parse(self, view, buffer):
        self.view = view
        self.buffer = buffer

        startTime = time.time()

        treemodel, handler = self.create_treemodel()
        self.treeview.set_model(treemodel)
        self.treeview.freeze_child_notify()

        visitor = OutlineTreeModelASTVisitor(treemodel)
 
        try:
            bounds = self.buffer.get_bounds()
            mod = compiler.parse(self.buffer.get_text(bounds[0], bounds[1]).replace('\r', '\n') + '\n')
            visitor.preorder(mod, visitor, None)
            del bounds, mod, visitor
        except SyntaxError:
            pass
        finally:
            gc.collect()

        treemodel.disconnect(handler)
        self.treeview.thaw_child_notify()

        stopTime = time.time()
        self.label.set_text('Outline created in ' + str(float(stopTime - startTime)) + ' s')


class PythonOutlinePluginInstance(object):
    def __init__(self, plugin, window):
        self._window = window
        self._plugin = plugin

        self._insert_panel()

    def deactivate(self):
        self._remove_panel

        self._window = None
        self._plugin = None

    def update_ui(self):
        document = self._window.get_active_document()
        if document:
            uri = str(document.get_uri())
            if document.get_mime_type() == 'text/x-python' or uri.endswith('.py') or uri.endswith('.pyw'):
                self.outlinebox.parse(self._window.get_active_view(), document)
            else:
                treemodel, handler = self.outlinebox.create_treemodel()
                self.outlinebox.treeview.set_model(treemodel)

    def _insert_panel(self):
        self.panel = self._window.get_side_panel()
        self.outlinebox = OutlineBox()
        self.panel.add_item(self.outlinebox, "Python Outline", gtk.STOCK_REFRESH)

    def _remove_panel(self):
        self.panel.destroy()


class PythonOutlinePlugin(gedit.Plugin):
    def __init__(self):
        gedit.Plugin.__init__(self)
        self._instances = {}

    def activate(self, window):
        self._instances[window] = PythonOutlinePluginInstance(self, window)

    def deactivate(self, window):
        self._instances[window].deactivate()
        del self._instances[window]

    def update_ui(self, window):
        self._instances[window].update_ui()
