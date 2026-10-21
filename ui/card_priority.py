from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QAbstractItemView,QPushButton,QDialogButtonBox
from python_macro.expedition_cards import priority_order


class CardPriorityDialog(QDialog):
    def __init__(self,order,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Expedition Card Priority')
        self.resize(380,430)
        layout=QVBoxLayout(self)
        hint=QLabel('Highest priority at the top. Drag categories or use Up / Down.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.list=QListWidget()
        self.list.addItems(priority_order(order))
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        layout.addWidget(self.list)
        row=QHBoxLayout()
        for label,offset in [('Up',-1),('Down',1)]:
            button=QPushButton(label)
            button.clicked.connect(lambda checked=False,step=offset:self.move_item(step))
            row.addWidget(button)
        layout.addLayout(row)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def move_item(self,step):
        row=self.list.currentRow()
        if 0<=row+step<self.list.count() and row>=0:
            item=self.list.takeItem(row)
            self.list.insertItem(row+step,item)
            self.list.setCurrentRow(row+step)

    def order(self):
        return [self.list.item(i).text() for i in range(self.list.count())]
