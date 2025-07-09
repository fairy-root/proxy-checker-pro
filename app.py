import customtkinter as ctk
import requests
import concurrent.futures
import threading
import re
import socket
import os
import signal
import sys
from time import time


WORKING_FILE = "working.txt"
DOWN_FILE = "down.txt"
SAVE_STATE_FILE = "proxy_state.txt"


class ProxyCheckerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Proxy Checker Pro")
        self.geometry("900x700")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.is_checking = False
        self.stop_event = threading.Event()
        self.thread_pool = None
        self.remaining_proxies = []
        self.checker_thread = None

        self.create_widgets()

        self.load_saved_state()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        """Create and layout all the GUI widgets."""

        top_frame = ctk.CTkFrame(self)
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        top_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top_frame, text="Proxy List:").grid(
            row=0, column=0, padx=10, pady=(10, 0), sticky="w"
        )
        self.proxy_textbox = ctk.CTkTextbox(top_frame, height=150)
        self.proxy_textbox.grid(
            row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew"
        )
        self.proxy_textbox.insert(
            "0.0",
            "(Http)45.250.255.25:10799:user:pass\n(Socks5)146.70.34.75:1090\n192.168.1.1:8080\n...",
        )
        self.add_context_menu(self.proxy_textbox)

        ctk.CTkLabel(top_frame, text="Target URL:").grid(
            row=2, column=0, padx=10, pady=(10, 0), sticky="w"
        )
        self.url_entry = ctk.CTkEntry(top_frame)
        self.url_entry.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="ew")
        self.url_entry.insert(0, "https://www.google.com")
        self.add_context_menu(self.url_entry)

        ctk.CTkLabel(
            top_frame, text="Validation Text (e.g., <title>Google</title>):"
        ).grid(row=4, column=0, padx=10, pady=(10, 0), sticky="w")
        self.title_entry = ctk.CTkEntry(top_frame)
        self.title_entry.grid(
            row=5, column=0, columnspan=2, padx=10, pady=5, sticky="ew"
        )
        self.title_entry.insert(0, "<title>Google</title>")
        self.add_context_menu(self.title_entry)

        controls_frame = ctk.CTkFrame(self)
        controls_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        controls_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.start_button = ctk.CTkButton(
            controls_frame, text="Start Checking", command=self.start_checking
        )
        self.start_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.stop_button = ctk.CTkButton(
            controls_frame,
            text="Stop",
            command=self.stop_checking,
            state="disabled",
            fg_color="#D32F2F",
            hover_color="#B71C1C",
        )
        self.stop_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.force_stop_button = ctk.CTkButton(
            controls_frame,
            text="Force Stop",
            command=self.force_stop_checking,
            state="disabled",
            fg_color="#8B0000",
            hover_color="#660000",
        )
        self.force_stop_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        self.clear_button = ctk.CTkButton(
            controls_frame,
            text="Clear",
            command=self.clear_all,
            fg_color="#616161",
            hover_color="#424242",
        )
        self.clear_button.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        results_frame = ctk.CTkFrame(self)
        results_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        results_frame.grid_columnconfigure(0, weight=1)
        results_frame.grid_rowconfigure(0, weight=1)

        self.results_textbox = ctk.CTkTextbox(
            results_frame, state="disabled", text_color="white"
        )
        self.results_textbox.grid(row=0, column=0, sticky="nsew")
        self.results_textbox.tag_config("green", foreground="#66BB6A")
        self.results_textbox.tag_config("red", foreground="#EF5350")
        self.results_textbox.tag_config("yellow", foreground="#FFEE58")
        self.results_textbox.tag_config("cyan", foreground="#26C6DA")
        self.add_context_menu(self.results_textbox)

        status_frame = ctk.CTkFrame(self)
        status_frame.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")
        status_frame.grid_columnconfigure(3, weight=1)

        self.working_label = ctk.CTkLabel(status_frame, text="Working: 0")
        self.working_label.grid(row=0, column=0, padx=10)

        self.down_label = ctk.CTkLabel(status_frame, text="Down: 0")
        self.down_label.grid(row=0, column=1, padx=10)

        self.loaded_label = ctk.CTkLabel(status_frame, text="Loaded: 0")
        self.loaded_label.grid(row=0, column=2, padx=10)

        self.progress_bar = ctk.CTkProgressBar(status_frame, orientation="horizontal")
        self.progress_bar.grid(row=0, column=3, padx=10, sticky="ew")
        self.progress_bar.set(0)

    def add_context_menu(self, widget):
        """Add right-click context menu to a widget."""
        menu = ctk.CTkFrame(
            self, fg_color="#2B2B2B", border_width=1, border_color="#404040"
        )
        menu.withdraw = lambda: menu.place_forget()

        def show_context_menu(event):

            try:
                menu.place_forget()
            except:
                pass

            for child in menu.winfo_children():
                child.destroy()

            has_selection = False
            is_textbox = isinstance(widget, ctk.CTkTextbox)
            is_entry = isinstance(widget, ctk.CTkEntry)

            try:
                if (
                    is_entry
                    and hasattr(widget, "selection_get")
                    and widget.selection_get()
                ):
                    has_selection = True
                elif (
                    is_textbox
                    and hasattr(widget, "tag_ranges")
                    and widget.tag_ranges("sel")
                ):
                    has_selection = True
            except:
                pass

            y_pos = 5

            if has_selection:
                copy_btn = ctk.CTkButton(
                    menu,
                    text="Copy",
                    width=80,
                    height=25,
                    command=lambda: self.copy_text(widget),
                    fg_color="#404040",
                    hover_color="#505050",
                )
                copy_btn.place(x=5, y=y_pos)
                y_pos += 30

            widget_is_disabled = False
            try:
                if is_textbox:

                    widget_is_disabled = not widget.cget("state") == "normal"
                elif is_entry:
                    widget_is_disabled = widget.cget("state") == "disabled"
            except:
                widget_is_disabled = False

            if has_selection and not widget_is_disabled:
                cut_btn = ctk.CTkButton(
                    menu,
                    text="Cut",
                    width=80,
                    height=25,
                    command=lambda: self.cut_text(widget),
                    fg_color="#404040",
                    hover_color="#505050",
                )
                cut_btn.place(x=5, y=y_pos)
                y_pos += 30

            if not widget_is_disabled:
                paste_btn = ctk.CTkButton(
                    menu,
                    text="Paste",
                    width=80,
                    height=25,
                    command=lambda: self.paste_text(widget),
                    fg_color="#404040",
                    hover_color="#505050",
                )
                paste_btn.place(x=5, y=y_pos)
                y_pos += 30

            select_all_btn = ctk.CTkButton(
                menu,
                text="Select All",
                width=80,
                height=25,
                command=lambda: self.select_all_text(widget),
                fg_color="#404040",
                hover_color="#505050",
            )
            select_all_btn.place(x=5, y=y_pos)
            y_pos += 30

            menu.configure(width=90, height=y_pos)
            try:
                x = event.x_root - self.winfo_rootx()
                y = event.y_root - self.winfo_rooty()
                menu.place(x=x, y=y)
                menu.lift()
            except:
                pass

        def hide_context_menu(event=None):
            menu.place_forget()

        widget.bind("<Button-3>", show_context_menu)

        self.bind("<Button-1>", hide_context_menu, add="+")

    def copy_text(self, widget):
        """Copy selected text to clipboard."""
        try:
            if hasattr(widget, "selection_get"):

                text = widget.selection_get()
            else:

                text = widget.get("sel.first", "sel.last")
            self.clipboard_clear()
            self.clipboard_append(text)
        except:
            pass

    def cut_text(self, widget):
        """Cut selected text to clipboard."""
        try:
            self.copy_text(widget)
            if hasattr(widget, "delete") and hasattr(widget, "selection_present"):
                if widget.selection_present():
                    widget.delete("sel.first", "sel.last")
            elif hasattr(widget, "delete") and hasattr(widget, "tag_ranges"):
                if widget.tag_ranges("sel"):
                    widget.delete("sel.first", "sel.last")
        except:
            pass

    def paste_text(self, widget):
        """Paste text from clipboard."""
        try:
            text = self.clipboard_get()
            if hasattr(widget, "insert"):
                if hasattr(widget, "selection_present") and widget.selection_present():
                    widget.delete("sel.first", "sel.last")
                elif hasattr(widget, "tag_ranges") and widget.tag_ranges("sel"):
                    widget.delete("sel.first", "sel.last")

                if hasattr(widget, "index") and hasattr(widget, "icursor"):

                    widget.insert(widget.index("insert"), text)
                else:

                    widget.insert("insert", text)
        except:
            pass

    def select_all_text(self, widget):
        """Select all text in widget."""
        try:
            if hasattr(widget, "select_range"):

                widget.select_range(0, "end")
            else:

                widget.tag_add("sel", "1.0", "end")
        except:
            pass

    def parse_proxy(self, proxy_line):
        proxy_line = proxy_line.strip()
        if not proxy_line:
            return None

        pattern_with_prefix = re.compile(r"\((\w+)\)([^:]+):(\d+)(?::([^:]+):(.*))?")
        match = pattern_with_prefix.match(proxy_line)

        if match:
            proto, host, port, user, password = match.groups()

            proto = proto.lower()
            if proto in ["sock4", "socks4"]:
                proto = "socks4"
            elif proto in ["socks5"]:
                proto = "socks5"
            elif proto in ["http", "https"]:
                proto = "http"
            else:
                return None
        else:

            pattern_without_prefix = re.compile(r"([^:]+):(\d+)(?::([^:]+):(.*))?")
            match = pattern_without_prefix.match(proxy_line)
            if not match:
                return None
            host, port, user, password = match.groups()
            proto = "http"

        return {
            "original": proxy_line,
            "protocol": proto,
            "host": host,
            "port": int(port),
            "user": user,
            "password": password,
        }

    def get_country(self, host):
        try:
            ip_address = socket.gethostbyname(host)
            response = requests.get(
                f"http://ip-api.com/json/{ip_address}?fields=country,countryCode",
                timeout=2,
            )
            data = response.json()
            return f"{data.get('country', 'N/A')} ({data.get('countryCode', 'N/A')})"
        except (socket.gaierror, requests.RequestException):
            return "N/A"

    def check_proxy(self, proxy_info, target_url, validation_text):
        if self.stop_event.is_set():
            return None
        protocol, host, port, user, password = (
            proxy_info["protocol"],
            proxy_info["host"],
            proxy_info["port"],
            proxy_info["user"],
            proxy_info["password"],
        )

        if protocol == "socks4":
            proxy_url = f"socks4://{host}:{port}"
        elif protocol == "socks5":
            if user and password:
                proxy_url = f"socks5://{user}:{password}@{host}:{port}"
            else:
                proxy_url = f"socks5://{host}:{port}"
        else:
            if user and password:
                proxy_url = f"http://{user}:{password}@{host}:{port}"
            else:
                proxy_url = f"http://{host}:{port}"

        proxies_dict = {"http": proxy_url, "https": proxy_url}
        result = {
            "proxy": proxy_info["original"],
            "status": "Inactive",
            "ping": -1,
            "country": "N/A",
            "error": "Unknown",
        }

        try:

            if self.stop_event.is_set():
                return None
            result["country"] = self.get_country(host)

            if self.stop_event.is_set():
                return None
            start_time = time()
            response = requests.get(
                target_url,
                proxies=proxies_dict,
                timeout=5,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            result["ping"] = round((time() - start_time) * 1000)
            if response.status_code == 200 and validation_text in response.text:
                result["status"] = "Active"
                result.pop("error")
            else:
                result["error"] = f"Validation Failed (Status: {response.status_code})"
        except requests.exceptions.ProxyError:
            result["error"] = "Proxy Error"
        except requests.exceptions.ConnectTimeout:
            result["error"] = "Timeout"
        except requests.exceptions.ConnectionError:
            result["error"] = "Connection Refused"
        except requests.exceptions.RequestException:
            result["error"] = "Request Error"
        except Exception:
            result["error"] = "Unknown Error"

        if self.stop_event.is_set():
            return None
        return result

    def update_ui_with_result(self, result):
        if not result:
            return

        if result["status"] == "Active":
            self.working_count += 1
            self.working_label.configure(text=f"Working: {self.working_count}")
        else:
            self.down_count += 1
            self.down_label.configure(text=f"Down: {self.down_count}")

        file_to_write = WORKING_FILE if result["status"] == "Active" else DOWN_FILE
        try:
            with open(file_to_write, "a") as f:
                f.write(result["proxy"] + "\n")
        except IOError as e:
            self.log_message(f"Error writing to {file_to_write}: {e}\n", "red")

        try:
            proxy_to_remove = result["proxy"]
            self.remaining_proxies = [
                p for p in self.remaining_proxies if p != proxy_to_remove
            ]
            self.update_proxy_textbox()
        except Exception as e:
            self.log_message(f"Error updating proxy list: {e}\n", "red")

        self.results_textbox.configure(state="normal")
        if result["status"] == "Active":
            self.results_textbox.insert("end", "Active   ", "green")
            self.results_textbox.insert(
                "end", f"| Ping: {result['ping']}ms ".ljust(15), "yellow"
            )

            if result["country"] != "N/A":
                self.results_textbox.insert(
                    "end", f"| Country: {result['country']} ".ljust(30), "cyan"
                )
            else:
                self.results_textbox.insert("end", "| ".ljust(30), "cyan")
            self.results_textbox.insert("end", f"| {result['proxy']}\n")
        else:
            self.results_textbox.insert("end", "Inactive ", "red")
            self.results_textbox.insert("end", f"| {result['error']}".ljust(48), "red")
            self.results_textbox.insert("end", f"| {result['proxy']}\n")
        self.results_textbox.configure(state="disabled")
        self.results_textbox.see("end")

        self.checked_count += 1
        if self.total_proxies > 0:
            progress = self.checked_count / self.total_proxies
            self.progress_bar.set(progress)

        if self.checked_count == self.total_proxies:
            self.on_checking_complete()

    def log_message(self, message, tag=None):
        self.results_textbox.configure(state="normal")
        if tag:
            self.results_textbox.insert("end", message, tag)
        else:
            self.results_textbox.insert("end", message)
        self.results_textbox.configure(state="disabled")
        self.results_textbox.see("end")

    def on_checking_complete(self):
        self.log_message("\n--- All proxies checked. ---\n", "green")
        self.toggle_controls(False)

        self.clear_saved_state()

    def update_proxy_textbox(self):
        """Update the proxy textbox with remaining proxies."""
        try:
            self.proxy_textbox.configure(state="normal")
            self.proxy_textbox.delete("1.0", "end")
            if self.remaining_proxies:
                proxy_text = "\n".join(self.remaining_proxies)
                self.proxy_textbox.insert("1.0", proxy_text)
            self.proxy_textbox.configure(
                state="disabled" if self.is_checking else "normal"
            )
        except Exception as e:
            self.log_message(f"Error updating proxy textbox: {e}\n", "red")

    def save_state(self):
        """Save current state when stopping midway."""
        try:
            if self.remaining_proxies:
                with open(SAVE_STATE_FILE, "w") as f:
                    for proxy in self.remaining_proxies:
                        f.write(proxy + "\n")
                self.log_message(
                    f"State saved: {len(self.remaining_proxies)} proxies remaining.\n",
                    "cyan",
                )
        except Exception as e:
            self.log_message(f"Error saving state: {e}\n", "red")

    def load_saved_state(self):
        """Load saved state on program start."""
        try:
            if os.path.exists(SAVE_STATE_FILE):
                with open(SAVE_STATE_FILE, "r") as f:
                    saved_proxies = [
                        line.strip() for line in f.readlines() if line.strip()
                    ]
                if saved_proxies:
                    self.proxy_textbox.delete("1.0", "end")
                    proxy_text = "\n".join(saved_proxies)
                    self.proxy_textbox.insert("1.0", proxy_text)
                    self.loaded_label.configure(text=f"Loaded: {len(saved_proxies)}")
                    self.log_message(
                        f"Loaded saved state: {len(saved_proxies)} proxies.\n", "cyan"
                    )
        except Exception as e:
            self.log_message(f"Error loading saved state: {e}\n", "red")

    def clear_saved_state(self):
        """Clear saved state file."""
        try:
            if os.path.exists(SAVE_STATE_FILE):
                os.remove(SAVE_STATE_FILE)
        except Exception as e:
            self.log_message(f"Error clearing saved state: {e}\n", "red")

    def start_checking(self):
        proxies_raw = self.proxy_textbox.get("1.0", "end-1c").strip().split("\n")
        self.target_url = self.url_entry.get().strip()
        self.validation_text = self.title_entry.get().strip()

        if not self.target_url or not self.validation_text:
            self.log_message(
                "Error: Target URL and Validation Text cannot be empty.\n", "red"
            )
            return

        proxies_to_check = [self.parse_proxy(p) for p in proxies_raw if p]
        proxies_to_check = [p for p in proxies_to_check if p is not None]

        if not proxies_to_check:
            self.log_message(
                "Error: No valid proxies found in the input list.\n", "red"
            )
            return

        self.clear_results()

        self.remaining_proxies = [line.strip() for line in proxies_raw if line.strip()]
        self.total_proxies = len(proxies_to_check)
        self.loaded_label.configure(text=f"Loaded: {self.total_proxies}")
        self.toggle_controls(True)
        self.log_message(f"Starting check on {self.total_proxies} proxies...\n")

        self.checker_thread = threading.Thread(
            target=self.run_checker_thread, args=(proxies_to_check,)
        )
        self.checker_thread.daemon = True
        self.checker_thread.start()

    def run_checker_thread(self, proxies):
        max_workers = min(50, len(proxies))

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers
            ) as executor:
                self.thread_pool = executor
                futures = {
                    executor.submit(
                        self.check_proxy, p, self.target_url, self.validation_text
                    )
                    for p in proxies
                }

                for future in concurrent.futures.as_completed(futures):
                    if self.stop_event.is_set():

                        for f in futures:
                            f.cancel()
                        break
                    try:
                        result = future.result()

                        self.after(0, self.update_ui_with_result, result)
                    except Exception as e:
                        self.after(
                            0,
                            self.log_message,
                            f"An error occurred in a worker thread: {e}\n",
                            "red",
                        )
        except Exception as e:
            self.after(0, self.log_message, f"Error in checker thread: {e}\n", "red")
        finally:

            self.thread_pool = None

            self.after(0, self.on_checking_complete)

    def stop_checking(self):
        if self.is_checking:
            self.log_message(
                "\n--- Stopping... waiting for active threads to finish. ---\n",
                "yellow",
            )
            self.stop_event.set()
            self.force_stop_button.configure(state="normal")

            shutdown_thread = threading.Thread(target=self._graceful_shutdown)
            shutdown_thread.daemon = True
            shutdown_thread.start()

    def _graceful_shutdown(self):
        """Handle graceful shutdown of thread pool."""
        if self.thread_pool:
            try:

                self.thread_pool.shutdown(wait=True, cancel_futures=True)
            except:
                pass
            finally:
                self.thread_pool = None
        self.after(0, self._finish_shutdown)

    def _finish_shutdown(self):
        """Finish the shutdown process on the main thread."""
        self.toggle_controls(False)
        self.log_message("--- Checking stopped. ---\n", "yellow")

        if self.remaining_proxies:
            self.save_state()

    def force_stop_checking(self):
        """Immediately force stop all checking operations."""
        if self.is_checking:
            self.log_message("\n--- Force stopping immediately! ---\n", "red")
            self.stop_event.set()

            if self.thread_pool:
                try:

                    self.thread_pool.shutdown(wait=False, cancel_futures=True)
                except:
                    pass
                finally:

                    self.thread_pool = None

            self.toggle_controls(False)
            self.log_message("--- Checking force stopped. ---\n", "red")

            if self.remaining_proxies:
                self.save_state()

    def clear_all(self):
        """Clears both inputs and results."""
        if self.is_checking:
            return
        self.proxy_textbox.delete("1.0", "end")
        self.remaining_proxies = []
        self.clear_results()

        self.clear_saved_state()

    def clear_results(self):
        """Clears only the results section."""
        self.results_textbox.configure(state="normal")
        self.results_textbox.delete("1.0", "end")
        self.results_textbox.configure(state="disabled")
        self.working_count = 0
        self.down_count = 0
        self.checked_count = 0
        self.total_proxies = 0
        self.working_label.configure(text="Working: 0")
        self.down_label.configure(text="Down: 0")
        self.loaded_label.configure(text="Loaded: 0")
        self.progress_bar.set(0)

    def toggle_controls(self, checking: bool):
        """Enable/disable UI elements based on checking state."""
        self.is_checking = checking
        state = "disabled" if checking else "normal"
        self.start_button.configure(state=state)
        self.clear_button.configure(state=state)
        self.proxy_textbox.configure(state=state)
        self.url_entry.configure(state=state)
        self.title_entry.configure(state=state)
        self.stop_button.configure(state="normal" if checking else "disabled")
        self.force_stop_button.configure(state="disabled")
        if not checking:
            self.stop_event.clear()

    def cleanup_threads(self):
        """Clean up all threads before application exit."""
        try:

            self.stop_event.set()

            if self.thread_pool:
                try:
                    self.thread_pool.shutdown(wait=False, cancel_futures=True)
                    self.thread_pool = None
                except:
                    pass

        except Exception as e:
            print(f"Error during cleanup: {e}")

    def on_closing(self):
        """Handle application closing."""
        try:

            if self.is_checking and self.remaining_proxies:
                self.save_state()

            self.cleanup_threads()

        except Exception as e:
            print(f"Error during closing: {e}")
        finally:

            self.destroy()


if __name__ == "__main__":

    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully"""
        print("Received interrupt signal. Cleaning up...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = ProxyCheckerApp()

    try:
        app.mainloop()
    except KeyboardInterrupt:
        print("Application interrupted by user")
        app.cleanup_threads()
    finally:

        if "app" in locals():
            app.cleanup_threads()
