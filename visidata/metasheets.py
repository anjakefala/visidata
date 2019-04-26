from visidata import globalCommand, BaseSheet, Column, options, vd, anytype, ENTER, asyncthread, option, Sheet
from visidata import CellColorizer, RowColorizer
from visidata import ColumnAttr, ColumnEnum, ColumnItem
from visidata import getGlobals, TsvSheet, Path, bindkeys, commands, composeStatus, Option
from visidata import undoAttr, undoAddCols, VisiData, vlen

globalCommand('^P', 'statuses', 'vd.push(StatusSheet("statusHistory"))')
globalCommand('gC', 'columns-all', 'vd.push(ColumnsSheet("all_columns", source=vd.sheets))')

BaseSheet.addCommand('zO', 'options-sheet', 'vd.push(sheet.optionsSheet)')
globalCommand('O', 'options-global', 'vd.push(vd.globalOptionsSheet)')
Sheet.addCommand('C', 'columns-sheet', 'vd.push(ColumnsSheet(name+"_columns", source=[sheet]))')
BaseSheet.addCommand('z^H', 'help-commands', 'vd.push(HelpSheet(name + "_commands", source=sheet, revbinds={}))')

option('visibility', 0, 'visibility level (0=low, 1=high)')

@BaseSheet.cached_property
def optionsSheet(sheet):
    return OptionsSheet(sheet.name+"_options", source=sheet)

@VisiData.cached_property
def globalOptionsSheet(vd):
    return OptionsSheet('global_options', source='override')


class StatusSheet(Sheet):
    precious = False
    rowtype = 'statuses'  # rowdef: (priority, args, nrepeats)
    columns = [
        ColumnItem('priority', 0, type=int, width=0),
        ColumnItem('nrepeats', 2, type=int, width=0),
        ColumnItem('args', 1, width=0),
        Column('message', getter=lambda col,row: composeStatus(row[1], row[2])),
    ]
    colorizers = [
        RowColorizer(1, 'color_error', lambda s,c,r,v: r and r[0] == 3),
        RowColorizer(1, 'color_warning', lambda s,c,r,v: r and r[0] in [1,2]),
    ]

    def reload(self):
        self.rows = vd.statusHistory[::-1]


class ColumnsSheet(Sheet):
    rowtype = 'columns'
    _rowtype = Column
    _coltype = ColumnAttr
    precious = False
    class ValueColumn(Column):
        'passthrough to the value on the source cursorRow'
        def calcValue(self, srcCol):
            return srcCol.getDisplayValue(srcCol.sheet.cursorRow)
        def setValue(self, srcCol, val):
            srcCol.setValue(srcCol.sheet.cursorRow, val)

    columns = [
            ColumnAttr('sheet', type=str),
            ColumnAttr('name', width=options.default_width),
            ColumnAttr('width', type=int),
            ColumnAttr('height', type=int, width=0),
            ColumnEnum('type', getGlobals(), default=anytype),
            ColumnAttr('fmtstr'),
            ValueColumn('value', width=options.default_width),
            Column('expr', getter=lambda col,row: getattr(row, 'expr', ''),
                           setter=lambda col,row,val: setattr(row, 'expr', val)),
            ColumnAttr('ncalcs', type=int, width=0, cache=False),
            ColumnAttr('maxtime', type=float, width=0, cache=False),
            ColumnAttr('totaltime', type=float, width=0, cache=False),
    ]
    nKeys = 2
    colorizers = [
        RowColorizer(7, 'color_key_col', lambda s,c,r,v: r and r.keycol),
        RowColorizer(8, 'color_hidden_col', lambda s,c,r,v: r and r.hidden),
    ]
    def reload(self):
        if len(self.source) == 1:
            self.rows = self.source[0].columns
            self.cursorRowIndex = self.source[0].cursorColIndex
            self.columns[0].hide()  # hide 'sheet' column if only one sheet
        else:
            self.rows = [col for vs in self.source for col in vs.visibleCols if vs is not self]

    def newRow(self):
        c = type(self.source[0])._coltype()
        c.sheet = self.source[0]
        return c

ColumnsSheet.addCommand(None, 'resize-source-rows-max', 'for c in selectedRows or [cursorRow]: c.width = c.getMaxWidth(source.visibleRows)')
ColumnsSheet.addCommand('&', 'join-cols', 'rows.insert(cursorRowIndex, combineColumns(selectedRows or fail("no columns selected to concatenate")))', undo=undoAddCols)


class HelpSheet(Sheet):
    'Show all commands available to the source sheet.'
    rowtype = 'commands'
    precious = False

    columns = [
        ColumnAttr('sheet'),
        ColumnAttr('longname'),
        Column('keystrokes', getter=lambda col,row: col.sheet.revbinds.get(row.longname)),
        Column('description', getter=lambda col,row: col.sheet.cmddict[(row.sheet, row.longname)].helpstr),
        ColumnAttr('execstr', width=0),
        ColumnAttr('logged', 'replayable', width=0),
    ]
    nKeys = 2
    @asyncthread
    def reload(self):
        from pkg_resources import resource_filename
        cmdlist = TsvSheet('cmdlist', source=Path(resource_filename(__name__, 'commands.tsv')))
        cmdlist.reload_sync()

        self.rows = []
        for (k, o), v in commands.iter(self.source):
            self.addRow(v)
            v.sheet = o

        self.cmddict = {}
        for cmdrow in cmdlist.rows:
            self.cmddict[(cmdrow.sheet, cmdrow.longname)] = cmdrow

        self.revbinds = {}  # [longname] -> keystrokes
        for (keystrokes, _), longname in bindkeys.iter(self.source):
            if keystrokes not in self.revbinds:
                self.revbinds[longname] = keystrokes


class OptionsSheet(Sheet):
    _rowtype = Option  # rowdef: Option
    rowtype = 'options'
    precious = False
    columns = (
        ColumnAttr('option', 'name'),
        Column('value',
            getter=lambda col,row: col.sheet.diffOption(row.name),
            setter=lambda col,row,val: options.set(row.name, val, col.sheet.source)),
        Column('default', getter=lambda col,row: options.get(row.name, 'global')),
        Column('description', width=40, getter=lambda col,row: options._get(row.name, 'global').helpstr),
        ColumnAttr('replayable'),
    )
    colorizers = [
        CellColorizer(3, None, lambda s,c,r,v: v.value if r and c in s.columns[1:3] and r.name.startswith('color_') else None),
    ]
    nKeys = 1

    def diffOption(self, optname):
        val = options.get(optname, self.source)
        default = options.get(optname, 'global')
        return val if val != default else ''

    def editOption(self, row):
        currentValue = options.get(row.name, self.source)
        if isinstance(row.value, bool):
            options.set(row.name, not currentValue, self.source)
        else:
            options.set(row.name, self.editCell(1, value=currentValue), self.source)

    def reload(self):
        self.rows = []
        for k in options.keys():
            opt = options._get(k)
            self.addRow(opt)
        self.columns[1].name = 'global_value' if self.source == 'override' else 'sheet_value'

OptionsSheet.addCommand(None, 'edit-option', 'editOption(cursorRow)', undo='lambda source=source,opt=cursorRow,val=options.get(cursorRow.name,source): options.set(opt.name, val, source)')

bindkeys.set('e', 'edit-option', OptionsSheet)
bindkeys.set(ENTER, 'edit-option', OptionsSheet)

def combineColumns(cols):
    'Return Column object formed by joining fields in given columns.'
    return Column("+".join(c.name for c in cols),
                  getter=lambda col,row,cols=cols,ch=' ': ch.join(c.getDisplayValue(row) for c in cols))

# used ColumnsSheet, affecting the 'row' (source column)
undoColTypes = undoAttr('selectedRows or [cursorRow]', 'type')
ColumnsSheet.addCommand('g!', 'key-selected', 'setKeys(selectedRows or [cursorRow])', undo=undoAttr('selectedRows or [cursorRow]', 'keycol'))
ColumnsSheet.addCommand('gz!', 'key-off-selected', 'unsetKeys(selectedRows or [cursorRow])', undo=undoAttr('selectedRows or [cursorRow]', 'keycol'))
ColumnsSheet.addCommand('g-', 'hide-selected', 'for c in selectedRows or [cursorRow]: c.hide()', undo=undoAttr('selectedRows or [cursorRow]', 'width'))
ColumnsSheet.addCommand('g%', 'type-float-selected', 'for c in selectedRows or [cursorRow]: c.type = float', undo=undoColTypes)
ColumnsSheet.addCommand('g#', 'type-int-selected', 'for c in selectedRows or [cursorRow]: c.type = int', undo=undoColTypes)
ColumnsSheet.addCommand('gz#', 'type-len-selected', 'for c in selectedRows or [cursorRow]: c.type = vlen', undo=undoColTypes)
ColumnsSheet.addCommand('g@', 'type-date-selected', 'for c in selectedRows or [cursorRow]: c.type = date', undo=undoColTypes)
ColumnsSheet.addCommand('g$', 'type-currency-selected', 'for c in selectedRows or [cursorRow]: c.type = currency', undo=undoColTypes)
ColumnsSheet.addCommand('g~', 'type-string-selected', 'for c in selectedRows or [cursorRow]: c.type = str', undo=undoColTypes)
ColumnsSheet.addCommand('gz~', 'type-any-selected', 'for c in selectedRows or [cursorRow]: c.type = anytype', undo=undoColTypes)
