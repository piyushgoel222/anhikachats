import os
import json
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

# Default parsed JSON location
DEFAULT_FILE_PATH = r"d:\vscode\igchatexport\joiner\data\parsed\Anshika_combined.json"

class VideoCallVisualTimelineApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Call Drag & Drop Timeline Joiner")
        self.root.geometry("1100x850")
        self.root.configure(bg="#1e1e1e")

        # Application state
        self.filepath = DEFAULT_FILE_PATH
        self.chat_data = None
        self.messages = []
        self.nodes = []      # List of dicts {index, timestamp, sender, direction, current_text}
        self.edges = set()   # Set of tuples (start_idx, end_idx)

        # Drag and Drop State
        self.dragging = False
        self.drag_start_node_idx = None  # index in self.nodes
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.temp_line = None

        # Theme Colors (Premium Dark UI)
        self.colors = {
            "bg": "#1e1e1e",
            "frame_bg": "#252526",
            "card_bg": "#1e1e1e",
            "card_border": "#3c3c3c",
            "text": "#d4d4d4",
            "text_bright": "#ffffff",
            "text_mute": "#8c8c8c",
            "connector_start": "#4ec9b0",  # Emerald Teal
            "connector_end": "#3b82f6",    # Bright Blue
            "link_normal": "#4ec9b0",      # Teal
            "link_warning": "#f43f5e",     # Crimson Red (>4h calls)
            "gap_color": "#d7ba7d",        # Gold
            "border": "#2d2d2d",
            "input_bg": "#3c3c3c"
        }

        self.setup_styles()
        self.create_widgets()
        self.load_json_file(self.filepath)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("Title.TLabel", background=self.colors["bg"], foreground=self.colors["text_bright"], font=("Segoe UI", 14, "bold"))
        style.configure("TButton", background=self.colors["input_bg"], foreground=self.colors["text"], borderwidth=1, focuscolor="none")
        style.map("TButton", background=[("active", self.colors["border"])])
        style.configure("Accent.TButton", background=self.colors["connector_start"], foreground=self.colors["bg"], font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#3ab098")])

    def create_widgets(self):
        # --- Top Menu Actions Bar ---
        top_bar = tk.Frame(self.root, bg=self.colors["frame_bg"], height=55, bd=1, relief="solid")
        top_bar.pack(fill="x", side="top")

        title = ttk.Label(top_bar, text="Timeline Cable Joiner", style="Title.TLabel", background=self.colors["frame_bg"])
        title.pack(side="left", padx=15, pady=10)

        # File actions grouping
        file_frame = tk.Frame(top_bar, bg=self.colors["frame_bg"])
        file_frame.pack(side="right", padx=15)

        self.path_var = tk.StringVar(value=self.filepath)
        path_ent = tk.Entry(file_frame, textvariable=self.path_var, width=35, 
                            bg=self.colors["input_bg"], fg=self.colors["text"], 
                            insertbackground=self.colors["text"], bd=1, relief="solid")
        path_ent.pack(side="left", padx=5, ipady=3)

        ttk.Button(file_frame, text="Browse", command=self.browse_file).pack(side="left", padx=2)
        ttk.Button(file_frame, text="Reload", command=lambda: self.load_json_file(self.path_var.get())).pack(side="left", padx=2)

        # Middle controls group
        ctrls_frame = tk.Frame(top_bar, bg=self.colors["frame_bg"])
        ctrls_frame.pack(side="right", padx=30)

        self.add_one_min_var = tk.BooleanVar(value=True)
        chk_min = tk.Checkbutton(
            ctrls_frame, 
            text="Add +1 min correction to new links", 
            variable=self.add_one_min_var, 
            bg=self.colors["frame_bg"], 
            fg=self.colors["text"],
            selectcolor=self.colors["frame_bg"],
            activebackground=self.colors["frame_bg"],
            activeforeground=self.colors["text"]
        )
        chk_min.pack(side="left", padx=10)

        ttk.Button(ctrls_frame, text="Auto-Suggest Consecutive", command=self.auto_suggest_edges).pack(side="left", padx=5)
        ttk.Button(ctrls_frame, text="Delete All Links", command=self.clear_all_edges).pack(side="left", padx=5)

        # --- Center Scrollable Canvas Viewport ---
        canvas_container = tk.Frame(self.root, bg=self.colors["bg"])
        canvas_container.pack(fill="both", expand=True, padx=15, pady=10)

        self.canvas = tk.Canvas(canvas_container, bg=self.colors["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Bind Mouse interactions on Canvas
        self.canvas.bind("<Button-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        
        # Mouse scroll bindings
        self.canvas.bind_all("<MouseWheel>", self.on_mouse_wheel)

        # --- Bottom Status Bar ---
        bottom_bar = tk.Frame(self.root, bg=self.colors["frame_bg"], height=40, bd=1, relief="solid")
        bottom_bar.pack(fill="x", side="bottom")

        # Legend representation
        legend_frame = tk.Frame(bottom_bar, bg=self.colors["frame_bg"])
        legend_frame.pack(side="left", padx=15, pady=8)

        # Left dot (End) indicator
        lbl_end_dot = tk.Label(legend_frame, text="● Left Dot: Call End (Receiver)", fg=self.colors["connector_end"], bg=self.colors["frame_bg"], font=("Segoe UI", 9, "bold"))
        lbl_end_dot.pack(side="left", padx=10)

        # Right dot (Start) indicator
        lbl_start_dot = tk.Label(legend_frame, text="● Right Dot: Call Start (Caller)", fg=self.colors["connector_start"], bg=self.colors["frame_bg"], font=("Segoe UI", 9, "bold"))
        lbl_start_dot.pack(side="left", padx=10)

        # Solid Green Link Legend
        lbl_link_norm = tk.Label(legend_frame, text="── Normal Link (<= 4 hrs)", fg=self.colors["link_normal"], bg=self.colors["frame_bg"], font=("Segoe UI", 9, "bold"))
        lbl_link_norm.pack(side="left", padx=10)

        # Dashed Red Link Legend
        lbl_link_warn = tk.Label(legend_frame, text="- - Warning Link (> 4 hrs)", fg=self.colors["link_warning"], bg=self.colors["frame_bg"], font=("Segoe UI", 9, "bold"))
        lbl_link_warn.pack(side="left", padx=10)

        # Status output text
        self.status_var = tk.StringVar(value="Ready.")
        status_lbl = tk.Label(bottom_bar, textvariable=self.status_var, fg=self.colors["text"], bg=self.colors["frame_bg"], font=("Segoe UI", 9, "italic"))
        status_lbl.pack(side="left", padx=30)

        # Main Save Button
        save_btn = ttk.Button(bottom_bar, text="Save Changes to File", style="Accent.TButton", command=self.save_changes_to_file)
        save_btn.pack(side="right", padx=15, pady=5)

        self.badge_var = tk.StringVar(value="0 active edges")
        badge_lbl = tk.Label(bottom_bar, textvariable=self.badge_var, fg=self.colors["connector_start"], bg=self.colors["frame_bg"], font=("Segoe UI", 10, "bold"))
        badge_lbl.pack(side="right", padx=10)

    # --- File Operations ---
    def browse_file(self):
        fpath = filedialog.askopenfilename(
            title="Open Instagram Parsed JSON",
            initialdir=os.path.dirname(DEFAULT_FILE_PATH),
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if fpath:
            self.path_var.set(fpath)
            self.load_json_file(fpath)

    def load_json_file(self, filepath):
        if not os.path.exists(filepath):
            self.status_var.set("File not found.")
            messagebox.showerror("Error", f"Could not find JSON file:\n{filepath}")
            return

        try:
            self.status_var.set("Loading JSON...")
            self.root.update_idletasks()

            with open(filepath, 'r', encoding='utf-8') as f:
                self.chat_data = json.load(f)

            self.filepath = filepath
            self.messages = self.chat_data.get("messages", [])
            self.edges.clear()

            # Parse nodes and reconstruct existing links
            self.scan_nodes_and_edges()
            self.redraw_timeline()
            self.update_status()

        except Exception as e:
            self.status_var.set("Failed to load JSON.")
            messagebox.showerror("Error", f"Failed to parse JSON file:\n{str(e)}")

    def scan_nodes_and_edges(self):
        """Identifies all video call events (nodes) and matches existing edges from bubble html."""
        self.nodes.clear()
        
        starts = []
        cuts = []

        for i, msg in enumerate(self.messages):
            html = msg.get("bubble_html", "")
            is_call = False
            role = "unlinked"

            if "[video_call_event]" in html:
                is_call = True
            elif "Video call started" in html:
                is_call = True
                role = "Start"
                starts.append(i)
            elif "Video call cut" in html:
                is_call = True
                role = "End"
                cuts.append(i)

            if is_call:
                self.nodes.append({
                    "index": i,
                    "timestamp": msg.get("timestamp"),
                    "sender": msg.get("sender_name") or "System",
                    "direction": msg.get("direction"),
                    "current_role": role,
                    "partner_index": None
                })

        # Pair reconstructed starts & cuts
        paired_cuts = set()
        for s in starts:
            match_c = None
            for c in cuts:
                if c > s and c not in paired_cuts:
                    match_c = c
                    break
            if match_c is not None:
                self.edges.add((s, match_c))
                paired_cuts.add(match_c)

        self.sync_node_attributes()

    def sync_node_attributes(self):
        """Coordinates Node roles and pointers based on the self.edges mappings."""
        # Reset
        for n in self.nodes:
            n["current_role"] = "unlinked"
            n["partner_index"] = None

        node_map = {n["index"]: n for n in self.nodes}
        for s, c in self.edges:
            if s in node_map and c in node_map:
                node_map[s]["current_role"] = "Start"
                node_map[s]["partner_index"] = c
                node_map[c]["current_role"] = "End"
                node_map[c]["partner_index"] = s

    # --- Math Helpers & Visual Strings ---
    def get_gap_string(self, ts1, ts2):
        """Returns readable representation of elapsed gap time between consecutive events."""
        if not ts1 or not ts2:
            return "Gap: N/A"
        try:
            dt1 = datetime.fromisoformat(ts1)
            dt2 = datetime.fromisoformat(ts2)
            delta = dt2 - dt1
            seconds = delta.total_seconds()
            if seconds < 0:
                return "Time Reversed!"
            
            minutes = int(seconds / 60)
            hours = minutes // 60
            mins = minutes % 60
            days = hours // 24
            hours = hours % 24

            if days > 0:
                return f"Gap: {days}d {hours}h {mins}m"
            elif hours > 0:
                return f"Gap: {hours}h {mins}m"
            return f"Gap: {mins}m"
        except:
            return "Gap: N/A"

    def get_duration_minutes(self, ts1, ts2):
        """Returns difference in minutes between two timestamps."""
        try:
            dt1 = datetime.fromisoformat(ts1)
            dt2 = datetime.fromisoformat(ts2)
            delta = dt2 - dt1
            return int(delta.total_seconds() / 60)
        except:
            return 0

    def get_duration_string(self, minutes):
        """Converts raw minutes to formatted 'X hr Y min' description."""
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours} hr {mins} min"
        return f"{mins} min"

    # --- Timeline Drawing Engine ---
    def redraw_timeline(self):
        """Clears and fully renders the graphical scrollable timeline on the Canvas."""
        self.canvas.delete("all")

        num_nodes = len(self.nodes)
        if num_nodes == 0:
            self.canvas.create_text(
                400, 150, 
                text="No video call events found in this chat JSON file.", 
                fill=self.colors["text_mute"], 
                font=("Segoe UI", 12)
            )
            return

        # Visual layout dimensions
        start_y = 60
        row_height = 50
        gap_height = 50
        card_w = 460
        start_x = 220
        end_x = start_x + card_w

        # Store graphic node coordinates for click tests and edge lines drawing
        self.rendered_coords = {} # index -> {left_connector: (x, y), right_connector: (x, y), rect_coords}

        current_y = start_y

        for i, node in enumerate(self.nodes):
            idx = node["index"]
            role = node["current_role"]
            ts = node["timestamp"] or "No Timestamp"
            sender = node["sender"]
            direction = node["direction"]

            # Calculate center Y coordinates for connectors
            center_y = current_y + (row_height // 2)

            # Node card coordinate bounds
            rect_coords = (start_x, current_y, end_x, current_y + row_height)

            # Left and Right connector center bounds
            left_connector = (start_x, center_y)
            right_connector = (end_x, center_y)

            # Cache coordinates
            self.rendered_coords[idx] = {
                "idx": i,
                "left": left_connector,
                "right": right_connector,
                "center_y": center_y
            }

            # 1. Draw Card Background Box
            card_fill = self.colors["frame_bg"]
            card_outline = self.colors["card_border"]
            
            # Apply dynamic highlight borders for linked nodes
            if role == "Start":
                card_outline = self.colors["connector_start"]
            elif role == "End":
                card_outline = self.colors["connector_end"]

            self.canvas.create_rectangle(
                rect_coords[0], rect_coords[1], rect_coords[2], rect_coords[3], 
                fill=card_fill, outline=card_outline, width=2
            )

            # 2. Draw Text on Card
            ts_disp = ts.replace("T", " ")
            card_title = f"#{idx} | {ts_disp} | {sender} ({direction})"
            
            # Draw content status preview
            preview_html = self.messages[idx].get("bubble_html", "")
            clean_text = "[video_call_event]"
            if "Video call started" in preview_html:
                clean_text = "Video call started"
            elif "Video call cut" in preview_html:
                if "after" in preview_html:
                    dur_val = preview_html.split("after")[1].split("</div>")[0].strip()
                    clean_text = f"Video call cut (after {dur_val})"
                else:
                    clean_text = "Video call cut"

            # Draw titles
            self.canvas.create_text(
                start_x + 15, current_y + 15, 
                text=card_title, anchor="w", 
                fill=self.colors["text_bright"], 
                font=("Segoe UI", 9, "bold")
            )
            self.canvas.create_text(
                start_x + 15, current_y + 35, 
                text=clean_text, anchor="w", 
                fill=self.colors["text_mute"], 
                font=("Segoe UI", 9)
            )

            # 3. Draw Left Connector Circle (End port)
            left_fill = self.colors["connector_end"] if role == "End" else self.colors["bg"]
            self.canvas.create_oval(
                left_connector[0] - 8, left_connector[1] - 8, 
                left_connector[0] + 8, left_connector[1] + 8, 
                fill=left_fill, outline=self.colors["connector_end"], width=2
            )

            # 4. Draw Right Connector Circle (Start port)
            right_fill = self.colors["connector_start"] if role == "Start" else self.colors["bg"]
            self.canvas.create_oval(
                right_connector[0] - 8, right_connector[1] - 8, 
                right_connector[0] + 8, right_connector[1] + 8, 
                fill=right_fill, outline=self.colors["connector_start"], width=2
            )

            # 5. Draw Time Gap and Divider to next node if not the last card
            if i < num_nodes - 1:
                next_node = self.nodes[i+1]
                gap_y_start = current_y + row_height
                gap_y_end = gap_y_start + gap_height
                mid_gap_y = gap_y_start + (gap_height // 2)

                # Draw dotted divider guide
                self.canvas.create_line(
                    start_x + (card_w // 2), gap_y_start, 
                    start_x + (card_w // 2), gap_y_end, 
                    fill="#3c3c3c", dash=(2, 3), width=1
                )

                # Calculate and write gap string
                gap_str = self.get_gap_string(ts, next_node["timestamp"])
                self.canvas.create_text(
                    start_x + (card_w // 2), mid_gap_y, 
                    text=gap_str, anchor="center", 
                    fill=self.colors["gap_color"], 
                    font=("Segoe UI", 9, "bold")
                )

            current_y += row_height + gap_height

        # 6. Draw Permanent Connection Cable Lines (Edges)
        node_map = {n["index"]: n for n in self.nodes}
        for s_idx, c_idx in self.edges:
            if s_idx in self.rendered_coords and c_idx in self.rendered_coords:
                pt_start = self.rendered_coords[s_idx]["right"]
                pt_end = self.rendered_coords[c_idx]["left"]

                # Calculate duration
                dur_mins = self.get_duration_minutes(node_map[s_idx]["timestamp"], node_map[c_idx]["timestamp"])
                
                # Check for > 4 hours notation (crimson dashed) instead of standard (solid teal)
                # (1 hr is normal, we now apply the requested notation rule strictly at > 4 hrs)
                is_long_call = dur_mins > 240 # 4 hours = 240 mins
                
                line_color = self.colors["link_warning"] if is_long_call else self.colors["link_normal"]
                line_dash = (6, 4) if is_long_call else None
                line_w = 3

                # Compute curved bezier coordinates
                # Smooth curve: starts right, loops down and enters from the left
                ctrl_x1 = pt_start[0] + 90
                ctrl_y1 = pt_start[1]
                ctrl_x2 = pt_end[0] - 90
                ctrl_y2 = pt_end[1]

                self.canvas.create_line(
                    pt_start[0], pt_start[1], 
                    ctrl_x1, ctrl_y1, 
                    ctrl_x2, ctrl_y2, 
                    pt_end[0], pt_end[1], 
                    fill=line_color, width=line_w, 
                    dash=line_dash, smooth=True
                )

                # Calculate curve midpoint coordinate to render visual details and interactive deletion handle
                # Cubic Bezier midpoint (t=0.5) formula calculation
                mx = 0.125 * pt_start[0] + 0.375 * ctrl_x1 + 0.375 * ctrl_x2 + 0.125 * pt_end[0]
                my = 0.125 * pt_start[1] + 0.375 * ctrl_y1 + 0.375 * ctrl_y2 + 0.125 * pt_end[1]

                # Draw duration text above handle
                dur_text = self.get_duration_string(dur_mins)
                if is_long_call:
                    dur_text = f"[!!! WARNING: {dur_text}]"

                self.canvas.create_text(
                    mx, my - 15, 
                    text=dur_text, anchor="center", 
                    fill=line_color, 
                    font=("Segoe UI", 9, "bold")
                )

                # Draw "X" Interactive Deletion Handle/Circle
                h_radius = 8
                self.canvas.create_oval(
                    mx - h_radius, my - h_radius, 
                    mx + h_radius, my + h_radius, 
                    fill=self.colors["link_warning"], outline=self.colors["text_bright"], width=1
                )
                self.canvas.create_text(
                    mx, my, 
                    text="x", anchor="center", 
                    fill=self.colors["text_bright"], 
                    font=("Segoe UI", 9, "bold")
                )

                # Cache hotzone to easily delete this edge on mouse click
                tag_name = f"del_edge_{s_idx}_{c_idx}"
                self.canvas.create_oval(
                    mx - 12, my - 12, 
                    mx + 12, my + 12, 
                    fill="", outline="", width=0, tags=tag_name
                )
                self.canvas.tag_bind(tag_name, "<Button-1>", lambda event, s=s_idx, c=c_idx: self.delete_edge(s, c))

        # Set scrollregion height dynamically to match coordinates
        self.canvas.configure(scrollregion=(0, 0, 900, current_y + 50))

    # --- Mouse Drag & Drop Linking Operations ---
    def on_canvas_press(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        # Check if click is on a start connector (Right Dot, X coordinate = start_x + card_w = 680)
        for idx, coords in self.rendered_coords.items():
            r_pt = coords["right"]
            
            # Distance test within 10 pixels radius
            dist = ((cx - r_pt[0]) ** 2 + (cy - r_pt[1]) ** 2) ** 0.5
            if dist <= 12:
                # Initiate dragging
                self.dragging = True
                self.drag_start_node_idx = coords["idx"]
                self.drag_start_x = r_pt[0]
                self.drag_start_y = r_pt[1]
                
                # Draw temporary drag cable
                self.temp_line = self.canvas.create_line(
                    self.drag_start_x, self.drag_start_y, cx, cy, 
                    fill=self.colors["connector_start"], width=2, dash=(3, 2)
                )
                return

    def on_canvas_drag(self, event):
        if not self.dragging:
            return
            
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        # Update temp cable line tip
        if self.temp_line:
            self.canvas.coords(self.temp_line, self.drag_start_x, self.drag_start_y, cx, cy)

    def on_canvas_release(self, event):
        if not self.dragging:
            return

        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)

        # Delete dragging cable
        if self.temp_line:
            self.canvas.delete(self.temp_line)
            self.temp_line = None

        # Check if dropped near a left connector (End port, coordinate X = start_x = 220)
        found_target = False
        for idx, coords in self.rendered_coords.items():
            l_pt = coords["left"]
            
            dist = ((cx - l_pt[0]) ** 2 + (cy - l_pt[1]) ** 2) ** 0.5
            if dist <= 14:
                target_node_idx = coords["idx"]
                start_node = self.nodes[self.drag_start_node_idx]
                target_node = self.nodes[target_node_idx]

                s_msg_idx = start_node["index"]
                t_msg_idx = target_node["index"]

                if s_msg_idx >= t_msg_idx:
                    self.status_var.set("Link Error: Cannot connect backward in timeline!")
                    messagebox.showerror("Sequence Error", "Drag path must start at earlier event and connect down the timeline to later event.")
                else:
                    self.create_edge(s_msg_idx, t_msg_idx)
                    found_target = True
                break

        if not found_target:
            self.status_var.set("Cable dropped in empty space.")

        self.dragging = False
        self.drag_start_node_idx = None

    # --- Edge Actions & Links Creators ---
    def create_edge(self, s_idx, c_idx):
        """Forms a call edge in memory between s_idx and c_idx. Overwrites overlapping edges if any."""
        # Check if either node is already linked, remove old links to maintain pure pairing
        old_edges_to_del = []
        for s, c in self.edges:
            if s == s_idx or c == c_idx or s == c_idx or c == s_idx:
                old_edges_to_del.append((s, c))

        for edge in old_edges_to_del:
            self.edges.discard(edge)

        # Add new edge
        self.edges.add((s_idx, c_idx))
        self.status_var.set(f"Linked Event #{s_idx} and #{c_idx}.")

        # Re-sync attributes and redraw visual UI
        self.sync_node_attributes()
        self.redraw_timeline()
        self.update_status()

    def delete_edge(self, s_idx, c_idx):
        """Splits an active edge back into unlinked nodes."""
        if (s_idx, c_idx) in self.edges:
            self.edges.discard((s_idx, c_idx))
            self.status_var.set(f"Deleted link between Event #{s_idx} and #{c_idx}.")
            
            self.sync_node_attributes()
            self.redraw_timeline()
            self.update_status()

    def auto_suggest_edges(self):
        """Quick scanner to automatically link all chronologically consecutive unlinked events."""
        unlinked_nodes = [n for n in self.nodes if n["current_role"] == "unlinked"]
        if len(unlinked_nodes) < 2:
            self.status_var.set("Not enough unlinked events found.")
            return

        confirm = messagebox.askyesno(
            "Auto-Suggest Links",
            "Do you want to automatically link consecutive unlinked events?\n\nThis provides a default layout. You can easily click the 'X' button on any long-duration line to split them."
        )
        if not confirm:
            return

        i = 0
        added = 0
        n_un = len(unlinked_nodes)

        while i < n_un - 1:
            n_start = unlinked_nodes[i]
            n_end = unlinked_nodes[i+1]
            
            t_start = n_start["timestamp"]
            t_end = n_end["timestamp"]

            if t_start and t_end:
                dur = self.get_duration_minutes(t_start, t_end)
                if dur >= 0:
                    self.edges.add((n_start["index"], n_end["index"]))
                    added += 1
                    i += 2  # Jump pairs
                    continue
            i += 1

        self.sync_node_attributes()
        self.redraw_timeline()
        self.update_status()
        self.status_var.set(f"Auto-suggested and connected {added} call edges.")

    def clear_all_edges(self):
        confirm = messagebox.askyesno(
            "Delete All",
            "Are you sure you want to delete all current active links in memory?\n\nAll call events will revert to unlinked."
        )
        if not confirm:
            return

        self.edges.clear()
        self.sync_node_attributes()
        self.redraw_timeline()
        self.update_status()
        self.status_var.set("All links deleted.")

    def update_status(self):
        self.badge_var.set(f"{len(self.edges)} links active")

    # --- Mouse scroll events inside Canvas ---
    def on_mouse_wheel(self, event):
        # standard scroll wheel behavior
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    # --- Save back to Instagram Chat JSON file ---
    def save_changes_to_file(self):
        confirm = messagebox.askyesno(
            "Save Changes",
            f"Are you sure you want to apply your changes to the JSON file?\n\nTarget File: {self.filepath}\n\nUnlinked nodes will stay or revert to unlinked [video_call_event] events."
        )
        if not confirm:
            return

        try:
            # 1. Create backup file
            backup_path = self.filepath + ".bak"
            if not os.path.exists(backup_path):
                self.status_var.set("Creating JSON file backup...")
                self.root.update_idletasks()
                shutil.copy2(self.filepath, backup_path)

            # 2. Re-map starts and ends
            start_indices = {s: c for s, c in self.edges}
            end_indices = {c: s for s, c in self.edges}
            node_dict = {n["index"]: n for n in self.nodes}

            # 3. Update bubble HTML properties of messages
            for n in self.nodes:
                idx = n["index"]
                msg = self.messages[idx]

                if idx in start_indices:
                    # Start of video call
                    msg["bubble_html"] = '<div class="bubble"><div class="unsup">Video call started</div></div>'
                elif idx in end_indices:
                    # End of video call
                    start_idx = end_indices[idx]
                    ts_start = node_dict[start_idx]["timestamp"]
                    ts_end = n["timestamp"]

                    add_min = self.add_one_min_var.get()
                    dur_mins = self.get_duration_minutes(ts_start, ts_end)
                    if add_min:
                        dur_mins += 1

                    dur_str = self.get_duration_string(dur_mins)
                    msg["bubble_html"] = f'<div class="bubble"><div class="unsup">Video call cut after {dur_str}</div></div>'
                else:
                    # Unlinked event
                    msg["bubble_html"] = '<div class="bubble"><div class="unsup">[video_call_event]</div></div>'

            # 4. Write back to disk
            self.status_var.set("Writing to JSON file...")
            self.root.update_idletasks()

            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.chat_data, f, ensure_ascii=False, indent=2)

            self.status_var.set("File saved successfully! Backup saved at Anshika_combined.json.bak")
            messagebox.showinfo("Success", "All changes have been successfully saved to the JSON file!\nReload your web app to view the updated timeline.")

            # Scan and redraw timeline from updated files to keep active sync
            self.scan_nodes_and_edges()
            self.redraw_timeline()
            self.update_status()

        except Exception as e:
            self.status_var.set("Save failed!")
            messagebox.showerror("Error", f"Failed to save changes to JSON file:\n{str(e)}")

# Main loop starter
if __name__ == "__main__":
    root = tk.Tk()
    app = VideoCallVisualTimelineApp(root)
    root.mainloop()
