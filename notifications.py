import win32api
import win32con
import win32gui
import os
import time
import threading

NIN_BALLOONUSERCLICK = win32con.WM_USER + 102  # system-defined ID for click on balloon


class WindowsNotifier:
    def __init__(self, click_callback=None):
        self.hwnd = None
        self.icon_id = 1
        self.class_name = "DocumentSIGnerNotify"
        self.click_callback = click_callback
        self._register_class()
        self._create_window()
        self._single_use_callback = False

    def _register_class(self):
        wc = win32gui.WNDCLASS()
        hInstance = win32api.GetModuleHandle(None)
        wc.hInstance = hInstance
        wc.lpszClassName = self.class_name
        wc.lpfnWndProc = self.wnd_proc
        try:
            win32gui.RegisterClass(wc)
        except win32gui.error:
            pass

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_DESTROY:
            self.hide()
            win32gui.PostQuitMessage(0)
        elif msg == win32con.WM_USER + 20:
            if lparam == NIN_BALLOONUSERCLICK and self.click_callback:
                self.click_callback()
                if getattr(self, "_single_use_callback", False):
                    self.click_callback = None
                    self._single_use_callback = False
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _create_window(self):
        hInstance = win32api.GetModuleHandle(None)
        self.hwnd = win32gui.CreateWindow(
            self.class_name,
            "DocumentSIGner Hidden",
            0,
            0,
            0,
            win32con.CW_USEDEFAULT,
            win32con.CW_USEDEFAULT,
            0,
            0,
            hInstance,
            None,
        )

    def set_notification_callback_once(self, callback):
        self.click_callback = callback
        self._single_use_callback = True

    def show_notification(self, title, msg, timeout=10):
        flags = win32gui.NIF_INFO | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        nid = (
            self.hwnd,
            self.icon_id,
            flags,
            win32con.WM_USER + 20,
            win32gui.LoadIcon(0, win32con.IDI_APPLICATION),
            "DocumentSIGner",
            msg,
            timeout * 1000,
            title,
        )
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)
        except:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
            except:
                pass

        threading.Timer(timeout, self.hide).start()

    def hide(self):
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, self.icon_id))
        except:
            pass

    def on_destroy(self, hwnd, msg, wparam, lparam):
        self.hide()
        win32gui.PostQuitMessage(0)


# Создаём глобальный экземпляр
notifier = WindowsNotifier()


def show_notification(title, msg, timeout=3):
    notifier.show_notification(title, msg, timeout)
