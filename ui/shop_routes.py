import json
from threading import Event
from pathlib import Path
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QFileDialog
from python_macro.shop_routes import MAPS


class ShopRoutesDialog(QDialog):
    def __init__(self,store,parent=None,busy=lambda:False):
        super().__init__(parent)
        self.store,self.busy=store,busy
        self.recorder=None
        self.setWindowTitle('Expedition Shop Routes')
        self.resize(470,280)
        layout=QVBoxLayout(self)
        hint=QLabel('Record one WASD route per map, from the payload to the shop. Use the macro camera setup. F3 or Stop Recording saves. Export a route to share it as a default.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.map=QComboBox()
        self.map.addItems(MAPS)
        self.map.currentTextChanged.connect(self.refresh)
        layout.addWidget(self.map)
        self.info=QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.record=QPushButton('Record Route')
        self.record.clicked.connect(self.toggle)
        layout.addWidget(self.record)
        row=QHBoxLayout()
        self.import_button=QPushButton('Import Route')
        self.export_button=QPushButton('Export Route')
        self.import_button.clicked.connect(self.import_route)
        self.export_button.clicked.connect(self.export_route)
        row.addWidget(self.import_button)
        row.addWidget(self.export_button)
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        try:
            data=self.store.load(self.map.currentText())
            self.info.setText(f"Saved WASD route: {data['path']['duration']:.1f} seconds." if data else 'No route saved for this map.')
            self.export_button.setEnabled(data is not None)
        except (OSError,ValueError) as error:
            self.info.setText(str(error))
            self.export_button.setEnabled(False)

    def controls(self,active):
        self.map.setEnabled(not active)
        self.import_button.setEnabled(not active)
        self.export_button.setEnabled(not active)
        self.record.setText('Stop Recording' if active else 'Record Route')

    def toggle(self):
        if self.recorder is not None and self.recorder.active:
            self.recorder.finish()
            return
        if self.busy():
            self.info.setText('Stop the macro before recording a shop route.')
            return
        try:
            from python_macro.capture import single_roblox_window
            from python_macro.input import RobloxClient
            from ui.path_recorder import PathRecorder
            target=single_roblox_window()
            if self.recorder is not None:
                self.recorder.deleteLater()
            self.recorder=PathRecorder(RobloxClient(target[0],Event(),selected_pid=target[2]),self)
            self.recorder.finished.connect(self.saved)
            self.recorder.failed.connect(self.failed)
            self.controls(True)
            self.recorder.start()
            if self.recorder.active:
                self.info.setText('Recording WASD. Press F3 near the shop to save.')
        except (OSError,RuntimeError,ValueError) as error:
            self.failed(str(error))

    def saved(self,raw):
        self.controls(False)
        try:
            if raw:
                self.store.save(self.map.currentText(),raw)
            self.refresh()
        except (OSError,ValueError) as error:
            self.failed(str(error))

    def failed(self,message):
        self.controls(False)
        self.info.setText(message)

    def import_route(self):
        name,_=QFileDialog.getOpenFileName(self,'Import shop route','','JSON routes (*.json)')
        if not name:
            return
        try:
            path=Path(name)
            if path.stat().st_size>2_000_000:
                raise ValueError('Route file is too large.')
            data=self.store.validate(json.loads(path.read_text(encoding='utf-8')),self.map.currentText())
            self.store.save(self.map.currentText(),data['path'])
            self.refresh()
        except (OSError,ValueError) as error:
            self.failed(str(error))

    def export_route(self):
        try:
            data=self.store.load(self.map.currentText())
            if data is None:
                return
            name,_=QFileDialog.getSaveFileName(self,'Export shop route',self.store.path(self.map.currentText()).name,'JSON routes (*.json)')
            if name:
                Path(name).write_text(json.dumps(data,indent=2),encoding='utf-8')
        except (OSError,ValueError) as error:
            self.failed(str(error))

    def done(self,result):
        if self.recorder is not None and self.recorder.active:
            self.recorder.finish()
        super().done(result)

    def closeEvent(self,event):
        if self.recorder is not None and self.recorder.active:
            self.recorder.finish()
        super().closeEvent(event)
