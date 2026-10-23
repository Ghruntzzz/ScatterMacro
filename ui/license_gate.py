"""Shared key gate and periodic online verification for launcher and macros."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from python_macro.licensing import check_session, restore_access
from ui.key_access import KeyAccess


def open_gate(app, factory, icon_path):
    gate = KeyAccess(icon_path)
    app.access_gate = gate
    executor = ThreadPoolExecutor(max_workers=1)
    app.access_executor = executor
    future = None
    active = False
    failed = False

    def unlocked(session):
        nonlocal active
        app.license_session = session
        app.licensed_window = factory()
        active = True
        heartbeat.start()

    def stop_application():
        # Stop automation cooperatively before closing Qt and its worker threads.
        running = False
        for window in app.topLevelWidgets():
            worker = getattr(window, 'worker', None)
            if worker is not None and worker.isRunning():
                running = True
                stop = getattr(window, '_stop_story', None)
                if stop:
                    stop()
            window.hide()
            window.setEnabled(False)
        if running:
            QTimer.singleShot(200, stop_application)
        else:
            QMessageBox.warning(None, 'Access verification', 'Access could not be verified. Automation has stopped. Reopen the launcher to activate your key or retry your connection.')
            app.quit()

    def poll():
        nonlocal future, failed
        if future is None or not future.done():
            return
        done, future = future, None
        try:
            session = done.result()
        except Exception:
            if active and not failed:
                failed = True
                heartbeat.stop()
                stop_application()
            elif not active:
                gate.unlock.setEnabled(True)
                gate.key.setEnabled(True)
                gate.status.setText('Enter your key to continue.')
        else:
            if not active:
                unlocked(session)
                gate.close()
            else:
                app.license_session = session

    def verify():
        nonlocal future
        if future is None and not failed:
            future = executor.submit(check_session)

    heartbeat = QTimer(app)
    heartbeat.setInterval(240000)
    heartbeat.timeout.connect(verify)
    polling = QTimer(app)
    polling.setInterval(100)
    polling.timeout.connect(poll)
    polling.start()
    app.aboutToQuit.connect(lambda: executor.shutdown(wait=False, cancel_futures=True))
    gate.unlocked.connect(unlocked)
    gate.show()
    if '--render-preview' in sys.argv:
        # Previews render only the locked screen; there is no activation bypass.
        path = Path(sys.argv[sys.argv.index('--render-preview') + 1]).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        def render():
            gate.grab().save(str(path))
            app.quit()
        QTimer.singleShot(300, render)
    else:
        gate.unlock.setEnabled(False)
        gate.key.setEnabled(False)
        gate.status.setText('Checking saved activation...')
        future = executor.submit(restore_access)
    return gate
