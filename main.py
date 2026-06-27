import os
import re
import json
import time
import base64
import threading
import webbrowser
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import customtkinter as ctk
import requests
from PIL import Image
import tidalapi
from tkinter import filedialog

# Theme and Color Scheme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class DownloadCard(ctk.CTkFrame):
    def __init__(self, master, track_name):
        super().__init__(master, corner_radius=10, fg_color="#1E1E28")
        self.pack(fill="x", padx=10, pady=6)
        
        self.title_lbl = ctk.CTkLabel(self, text=track_name, font=("Segoe UI", 12, "bold"), text_color="#E0E0E0", anchor="w")
        self.title_lbl.pack(fill="x", padx=10, pady=(8, 2))
        
        self.progress = ctk.CTkProgressBar(self, height=6, progress_color="#00b4d8")
        self.progress.set(0)
        self.progress.pack(fill="x", padx=10, pady=4)
        
        self.status_lbl = ctk.CTkLabel(self, text="Queued...", font=("Segoe UI", 10), text_color="#A0A0B0", anchor="w")
        self.status_lbl.pack(fill="x", padx=10, pady=(0, 8))

    def update_progress(self, value, text, color="#A0A0B0"):
        self.progress.set(value)
        self.status_lbl.configure(text=text, text_color=color)
        if value >= 1.0:
            self.progress.configure(progress_color="#4CAF50")
        elif value == 0.0 and color == "#e63946":
            self.progress.configure(progress_color="#e63946")


class TidalApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Tidal Downloader")
        self.geometry("1350x850")
        
        self.session = tidalapi.Session()
        try:
            self.session.audio_quality = tidalapi.Quality.HIGH
        except AttributeError:
            pass 
        
        self.executor = ThreadPoolExecutor(max_workers=3) 
        self.settings_file = os.path.join(os.getcwd(), "tidal_settings.json")
        
        self.current_playlist = None
        self.current_tracks = []
        
        self.load_settings()
        
        if self.load_session_data():
            self.build_main_ui()
        else:
            self.build_login_screen()

    # --- Settings Management ---
    def load_settings(self):
        self.download_dir = os.path.join(os.getcwd(), "Tidal_Downloads")
        self.audio_format = "Original (M4A/FLAC)"
        
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    data = json.load(f)
                    if data.get("download_dir") and os.path.exists(data.get("download_dir")):
                        self.download_dir = data.get("download_dir")
                    self.audio_format = data.get("audio_format", "Original (M4A/FLAC)")
            except Exception: pass
        os.makedirs(self.download_dir, exist_ok=True)
        
    def save_settings(self):
        try:
            data = {}
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r") as f:
                    data = json.load(f)
            data["download_dir"] = self.download_dir
            data["audio_format"] = self.audio_format
            with open(self.settings_file, "w") as f:
                json.dump(data, f)
        except Exception: pass
        
    def load_session_data(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    data = json.load(f)
                if data.get("access_token"):
                    if data.get("session_id"):
                        self.session.session_id = data.get("session_id")
                    self.session.load_oauth_session(
                        data.get("token_type", "Bearer"),
                        data.get("access_token"),
                        data.get("refresh_token")
                    )
                    return self.session.check_login()
            except Exception: pass
        return False

    def save_session_data(self):
        try:
            data = {"download_dir": self.download_dir, "audio_format": self.audio_format}
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r") as f:
                    try: data.update(json.load(f))
                    except Exception: pass
            
            data.update({
                "session_id": getattr(self.session, "session_id", ""),
                "access_token": getattr(self.session, "access_token", ""),
                "refresh_token": getattr(self.session, "refresh_token", ""),
                "token_type": getattr(self.session, "token_type", "Bearer"),
            })
            with open(self.settings_file, "w") as f:
                json.dump(data, f)
        except Exception: pass

    def logout(self):
        if os.path.exists(self.settings_file):
            with open(self.settings_file, "r") as f:
                data = json.load(f)
            for key in ["session_id", "access_token", "refresh_token", "token_type"]:
                data.pop(key, None)
            with open(self.settings_file, "w") as f:
                json.dump(data, f)
        self.session = tidalapi.Session()
        for widget in self.winfo_children():
            widget.destroy()
        self.build_login_screen()

    # --- UI Building ---
    def build_login_screen(self):
        self.grid_columnconfigure((0, 1, 2), weight=0) 
        self.login_frame = ctk.CTkFrame(self, corner_radius=20, fg_color="#181822")
        self.login_frame.place(relx=0.5, rely=0.5, anchor="center")

        title = ctk.CTkLabel(self.login_frame, text="Tidal Downloader", font=("Segoe UI", 36, "bold"), text_color="#00b4d8")
        title.pack(pady=(40, 10), padx=60)

        self.login_instructions = ctk.CTkLabel(
            self.login_frame, text="Welcome. Click below to authenticate your device.\nYour web browser will open automatically.", font=("Segoe UI", 16)
        )
        self.login_instructions.pack(pady=20, padx=40)

        self.login_btn = ctk.CTkButton(
            self.login_frame, text="Login to Tidal", font=("Segoe UI", 16, "bold"), 
            width=220, height=50, corner_radius=25, command=self.start_login, fg_color="#0077b6", hover_color="#0096c7"
        )
        self.login_btn.pack(pady=(10, 40))

    def start_login(self):
        self.login_btn.configure(state="disabled", text="Waiting for Auth...")
        threading.Thread(target=self._auth_thread, daemon=True).start()

    def _auth_thread(self):
        try:
            login, future = self.session.login_oauth()
            auth_url = getattr(login, "verification_uri_complete", None) or getattr(login, "verification_uri", None) or login
            webbrowser.open(auth_url)
            self.after(0, lambda: self.login_instructions.configure(text="Browser opened.\nPlease click 'Confirm' on the website."))
            future.result()
            if self.session.check_login():
                self.save_session_data()
                self.after(0, self.login_frame.destroy)
                self.after(0, self.build_main_ui)
            else:
                self.after(0, lambda: self.login_instructions.configure(text="Login validation failed."))
                self.after(0, lambda: self.login_btn.configure(state="normal", text="Retry Login"))
        except Exception as e:
            self.after(0, lambda: self.login_instructions.configure(text=f"Login failed: {str(e)}"))
            self.after(0, lambda: self.login_btn.configure(state="normal", text="Retry Login"))

    def build_main_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=260) 
        self.grid_columnconfigure(1, weight=1)              
        self.grid_columnconfigure(2, weight=0, minsize=320) 
        self.grid_rowconfigure(0, weight=1)

        # --- LEFT SIDEBAR ---
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color="#121218")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(2, weight=1) 

        user_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        user_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(30, 20))
        ctk.CTkLabel(user_frame, text="👤", font=("Segoe UI", 36)).pack(side="left")
        
        username = getattr(getattr(self.session, 'user', None), 'username', 'Tidal User') or 'Tidal User'
        user_info = ctk.CTkFrame(user_frame, fg_color="transparent")
        user_info.pack(side="left", padx=10)
        ctk.CTkLabel(user_info, text=username, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ctk.CTkButton(user_info, text="Logout", width=60, height=20, corner_radius=10, fg_color="#e63946", hover_color="#b52c38", font=("Segoe UI", 10, "bold"), command=self.logout).pack(anchor="w", pady=(2,0))

        ctk.CTkLabel(self.sidebar, text="Your Playlists", font=("Segoe UI", 16, "bold"), text_color="#A0A0B0").grid(row=1, column=0, sticky="w", padx=20, pady=(10, 5))
        self.playlist_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent", corner_radius=0)
        self.playlist_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        threading.Thread(target=self.load_playlists, daemon=True).start()

        # --- MAIN CONTENT ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=20, fg_color="#1A1A24")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_rowconfigure(3, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        top_bar = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=60)
        top_bar.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        top_bar.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(top_bar, placeholder_text="Search tracks, albums, or artists...", font=("Segoe UI", 16), height=45, corner_radius=22, border_width=1, border_color="#3b3b4f", fg_color="#222230")
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 15))
        self.search_entry.bind("<Return>", lambda event: self.start_search())
        ctk.CTkButton(top_bar, text="Search", font=("Segoe UI", 14, "bold"), width=100, height=45, corner_radius=22, fg_color="#0077b6", hover_color="#0096c7", command=self.start_search).grid(row=0, column=1)

        dir_frame = ctk.CTkFrame(self.main_frame, fg_color="#222230", corner_radius=15)
        dir_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 15))
        dir_frame.grid_columnconfigure(0, weight=1)
        self.dir_lbl = ctk.CTkLabel(dir_frame, text=f"Save to: {self.download_dir}", font=("Segoe UI", 13), text_color="#A0A0B0")
        self.dir_lbl.grid(row=0, column=0, sticky="w", padx=15, pady=10)
        
        self.format_menu = ctk.CTkOptionMenu(dir_frame, values=["Original (M4A/FLAC)", "MP3", "WAV"], width=140, height=30, corner_radius=15, fg_color="#3b3b4f", button_color="#4b4b6f", button_hover_color="#5b5b7f", command=self.change_format)
        self.format_menu.set(self.audio_format)
        self.format_menu.grid(row=0, column=1, padx=10, pady=10)
        ctk.CTkButton(dir_frame, text="Change Folder", width=120, height=30, corner_radius=15, fg_color="#3b3b4f", hover_color="#4b4b6f", command=self.change_directory).grid(row=0, column=2, padx=15, pady=10)

        self.sub_top_bar = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.sub_top_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.view_title = ctk.CTkLabel(self.sub_top_bar, text="Dashboard", font=("Segoe UI", 20, "bold"), text_color="#FFFFFF")
        self.view_title.grid(row=0, column=0, sticky="w")
        self.dl_all_btn = ctk.CTkButton(self.sub_top_bar, text="Download All", font=("Segoe UI", 12, "bold"), height=30, width=120, corner_radius=15, fg_color="#0077b6", hover_color="#0096c7", command=self.download_all_current)
        self.dl_all_btn.grid(row=0, column=1, padx=20)
        self.dl_all_btn.grid_remove()

        self.results_scroll = ctk.CTkScrollableFrame(self.main_frame, corner_radius=15, fg_color="transparent")
        self.results_scroll.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))

        # --- RIGHT SIDEBAR ---
        self.dl_sidebar = ctk.CTkFrame(self, corner_radius=0, fg_color="#121218", width=320)
        self.dl_sidebar.grid(row=0, column=2, sticky="nsew")
        self.dl_sidebar.grid_rowconfigure(1, weight=1)

        dl_header = ctk.CTkFrame(self.dl_sidebar, fg_color="transparent")
        dl_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(30, 10))
        ctk.CTkLabel(dl_header, text="Downloads", font=("Segoe UI", 18, "bold"), text_color="#A0A0B0").pack(side="left")
        ctk.CTkButton(dl_header, text="Clear", width=50, height=24, corner_radius=12, fg_color="#3b3b4f", hover_color="#4b4b6f", font=("Segoe UI", 11), command=self.clear_downloads).pack(side="right")
        self.dl_scroll = ctk.CTkScrollableFrame(self.dl_sidebar, fg_color="transparent", corner_radius=0)
        self.dl_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    # --- Logic Methods ---
    def change_directory(self):
        new_dir = filedialog.askdirectory(initialdir=self.download_dir, title="Select Download Folder")
        if new_dir:
            self.download_dir = new_dir
            self.dir_lbl.configure(text=f"Save to: {self.download_dir}")
            self.save_settings()

    def change_format(self, choice):
        self.audio_format = choice
        self.save_settings()

    def clear_downloads(self):
        for widget in self.dl_scroll.winfo_children():
            widget.destroy()

    def load_playlists(self):
        try:
            playlists = self.session.user.playlists()
            if not playlists: return
            for pl in playlists:
                self.after(0, self.add_playlist_card, pl)
        except: pass

    def add_playlist_card(self, playlist):
        ctk.CTkButton(self.playlist_scroll, text=f"🎵 {playlist.name}", font=("Segoe UI", 13), anchor="w", fg_color="transparent", hover_color="#2b2b3b", text_color="#E0E0E0", height=35, command=lambda p=playlist: self.show_playlist_overview(p)).pack(fill="x", pady=2)

    def show_playlist_overview(self, playlist):
        self.view_title.configure(text=f"Playlist: {playlist.name}")
        self.dl_all_btn.grid(row=0, column=1, padx=20) 
        self.current_playlist = playlist
        self.current_tracks = []
        for widget in self.results_scroll.winfo_children(): widget.destroy()
        threading.Thread(target=self._load_playlist_tracks, args=(playlist,), daemon=True).start()

    def _load_playlist_tracks(self, playlist):
        try:
            self.current_tracks = playlist.tracks()
            limit = min(len(self.current_tracks), 100)
            for i in range(limit): self.after(i * 15, self.add_track_card, self.current_tracks[i])
        except: pass

    def download_all_current(self):
        if not self.current_tracks: return
        subfolder = getattr(self.current_playlist, 'name', None)
        for track in self.current_tracks: self.queue_download(track, subfolder)

    def start_search(self):
        query = self.search_entry.get().strip()
        if not query: return
        self.view_title.configure(text=f"Search Results: {query}")
        self.dl_all_btn.grid_remove() 
        self.current_playlist, self.current_tracks = None, []
        for widget in self.results_scroll.winfo_children(): widget.destroy()
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            tracks = self.session.search(query).get('tracks', [])
            for i, track in enumerate(tracks[:30]): self.after(i * 15, self.add_track_card, track)
        except: pass

    def add_track_card(self, track):
        card = ctk.CTkFrame(self.results_scroll, corner_radius=12, fg_color="#262635")
        card.pack(fill="x", padx=10, pady=6)
        card.grid_columnconfigure(1, weight=1)
        cover_lbl = ctk.CTkLabel(card, text="♪", font=("Segoe UI", 24), width=50, height=50, corner_radius=8, fg_color="#181822")
        cover_lbl.grid(row=0, column=0, padx=10, pady=10)
        
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(info_frame, text=track.name, font=("Segoe UI", 15, "bold"), text_color="#FFFFFF").pack(anchor="w")
        ctk.CTkLabel(info_frame, text=f"{track.artist.name} • {track.album.name}", font=("Segoe UI", 13), text_color="#A0A0B0").pack(anchor="w")

        subfolder = getattr(self.current_playlist, 'name', None) if self.current_playlist else None
        ctk.CTkButton(card, text="Download", font=("Segoe UI", 13, "bold"), corner_radius=15, width=100, height=35, fg_color="#00b4d8", hover_color="#0096c7", command=lambda t=track, s=subfolder: self.queue_download(t, s)).grid(row=0, column=2, padx=15)
        self.executor.submit(self.load_cover_image, track, cover_lbl)

    def load_cover_image(self, track, label_widget):
        try:
            url = track.album.image(320)
            if url:
                img_data = Image.open(BytesIO(requests.get(url, timeout=5).content))
                ctk_img = ctk.CTkImage(light_image=img_data, dark_image=img_data, size=(50, 50))
                self.after(0, lambda: label_widget.configure(image=ctk_img, text=""))
        except: pass

    # --- Core Downloading & Built-in Conversion Logic ---
    def queue_download(self, track, subfolder=None):
        card_ui = DownloadCard(self.dl_scroll, track.name)
        self.executor.submit(self._download_worker, track, subfolder, card_ui)

    def get_track_stream_url(self, track):
        try:
            stream = self.session.track(track.id).get_stream()
            if hasattr(stream, 'get_urls') and callable(stream.get_urls):
                urls = stream.get_urls()
                if urls and isinstance(urls, list) and len(urls) > 0: return urls[0]
            if hasattr(stream, 'url') and stream.url: return stream.url
            if hasattr(stream, 'stream_url') and stream.stream_url: return stream.stream_url
            if hasattr(stream, 'manifest') and stream.manifest:
                try:
                    manifest_str = base64.b64decode(stream.manifest).decode('utf-8')
                    if manifest_str.startswith('{'):
                        data = json.loads(manifest_str)
                        if 'urls' in data and len(data['urls']) > 0: return data['urls'][0]
                    elif '<BaseURL>' in manifest_str:
                        match = re.search(r'<BaseURL>(.*?)</BaseURL>', manifest_str)
                        if match: return match.group(1)
                except: pass
        except: pass
        return None

    def clean_filename_string(self, text):
        return re.sub(r'[\\/*?:"<>|]', "", text).strip()

    def _download_worker(self, track, subfolder, card_ui):
        try:
            time.sleep(1.0) 
            self.after(0, lambda: card_ui.update_progress(0.05, "Locating stream..."))
            
            stream_url = self.get_track_stream_url(track)
            if not stream_url:
                self.after(0, lambda: card_ui.update_progress(0.0, "Blocked (DRM/Not Found)", "#e63946"))
                return

            safe_title = self.clean_filename_string(track.name)
            safe_artist = self.clean_filename_string(track.artist.name)
            
            dl_path = self.download_dir
            if subfolder:
                safe_sub = self.clean_filename_string(subfolder)
                dl_path = os.path.join(self.download_dir, safe_sub)
                os.makedirs(dl_path, exist_ok=True)
                
            original_ext = ".flac" if "flac" in stream_url.lower() else ".m4a"
            filename = f"{safe_artist} - {safe_title}{original_ext}"
            filepath = os.path.join(dl_path, filename)

            self.after(0, lambda: card_ui.update_progress(0.1, "Downloading...", "#00b4d8"))
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            
            with requests.get(stream_url, stream=True, headers=headers) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                last_update = time.time()
                
                with open(filepath, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=16384): 
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            if now - last_update > 0.2:
                                if total_size > 0:
                                    progress = min((downloaded / total_size) * 0.95, 0.95)
                                    self.after(0, lambda p=progress: card_ui.progress.set(p))
                                last_update = now

            # --- FFmpeg Conversion directly via OS ---
            final_file = filename
            if self.audio_format != "Original (M4A/FLAC)":
                self.after(0, lambda: card_ui.update_progress(0.95, f"Converting to {self.audio_format}...", "#F4A261"))
                
                if not shutil.which("ffmpeg"):
                    self.after(0, lambda: card_ui.update_progress(1.0, f"Saved Original (FFmpeg missing)", "#F4A261"))
                    return
                
                try:
                    ext = ".mp3" if self.audio_format == "MP3" else ".wav"
                    new_filepath = filepath.rsplit(".", 1)[0] + ext
                    
                    # Prevents the black CMD box from flashing on Windows
                    startupinfo = None
                    if os.name == 'nt':
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                    subprocess.run(
                        ["ffmpeg", "-y", "-i", filepath, new_filepath],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        startupinfo=startupinfo,
                        check=True
                    )
                    os.remove(filepath) 
                    final_file = os.path.basename(new_filepath)
                except Exception as ex:
                    print(f"Conversion Error: {ex}")

            self.after(0, lambda: card_ui.update_progress(1.0, f"Saved: {final_file}", "#4CAF50"))

        except Exception as e:
            self.after(0, lambda: card_ui.update_progress(0.0, "Error during download", "#e63946"))
            print(f"❌ Error for {track.name}: {str(e)}")

if __name__ == "__main__":
    app = TidalApp()
    app.mainloop()