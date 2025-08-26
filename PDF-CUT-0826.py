import fitz  # PyMuPDF，用於處理 PDF 檔案
import tkinter as tk  # GUI 主架構
from tkinter import ttk, filedialog, messagebox, simpledialog  # GUI 元件
from PIL import Image, ImageTk  # 圖片處理
import os  # 檔案路徑處理


class PDFCropper:
    def __init__(self, master):
        master.title("PDF 多選區裁切工具 (10x15cm)     設計:DY ")

        # 初始化狀態變數
        self.pdf_path = None
        self.doc = None
        self.current_page_index = 0
        self.crop_rects = []  # 儲存所有裁切區座標
        self.start_x = None
        self.start_y = None
        self.zoom = 1.0
        self.enable_batch = tk.BooleanVar(value=True)  # 是否啟用批次處理
        self.image_offset = (0, 0)  # 用於圖片置中顯示

        # 流水號相關
        self.serial_start_var = tk.IntVar(value=1)  # 預設起始流水號
        self.serial_counter = None  # 實際計算用

        # 建立上方功能列
        btn_frame = ttk.Frame(master, padding=10)
        btn_frame.pack(side=tk.TOP, fill=tk.X)

        style = ttk.Style()
        style.configure('TButton', font=('微軟正黑體', 11))
        style.configure('TCheckbutton', font=('微軟正黑體', 11))
        style.configure('TLabel', font=('微軟正黑體', 11))

        # 各按鈕功能
        self.btn_open = ttk.Button(btn_frame, text="開啟 PDF", command=self.load_pdf)
        self.btn_export = ttk.Button(btn_frame, text="匯出裁切區", command=self.export_crops)
        self.btn_prev = ttk.Button(btn_frame, text="上一頁", command=self.prev_page)
        self.btn_next = ttk.Button(btn_frame, text="下一頁", command=self.next_page)
        self.btn_clear = ttk.Button(btn_frame, text="清除選取區", command=self.clear_crops)
        self.btn_undo = ttk.Button(btn_frame, text="返回上一步", command=self.undo_crop)

        # 排列按鈕
        self.btn_open.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_export.pack(side=tk.LEFT, padx=(0, 12))
        self.btn_prev.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_next.pack(side=tk.LEFT, padx=(0, 12))
        self.btn_clear.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_undo.pack(side=tk.LEFT, padx=(0, 16))

        self.batch_checkbox = ttk.Checkbutton(btn_frame, text="批次多頁處理", variable=self.enable_batch)
        self.batch_checkbox.pack(side=tk.LEFT, padx=(0, 12))

        # 起始流水號輸入框
        ttk.Label(btn_frame, text="起始流水號:").pack(side=tk.LEFT, padx=(10, 4))
        self.serial_entry = ttk.Entry(btn_frame, textvariable=self.serial_start_var, width=6)
        self.serial_entry.pack(side=tk.LEFT)

        # 中間 PDF 預覽畫布區
        canvas_frame = ttk.Frame(master, padding=10)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#222222", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 狀態列
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(master, textvariable=self.status_var, relief=tk.SUNKEN, anchor='w', padding=5)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # 滑鼠與畫布事件綁定
        self.canvas.bind("<MouseWheel>", self.on_mousewheel_zoom)
        self.canvas.bind("<Button-4>", self.on_mousewheel_zoom)
        self.canvas.bind("<Button-5>", self.on_mousewheel_zoom)
        self.canvas.bind("<ButtonPress-1>", self.start_crop)
        self.canvas.bind("<B1-Motion>", self.draw_crop)
        self.canvas.bind("<ButtonRelease-1>", self.save_crop)
        self.master = master
        self.master.bind("<Configure>", lambda e: self.show_page())

        self.update_status()

    def update_status(self):
        """更新底部狀態列文字"""
        page_num = self.current_page_index + 1 if self.doc else 0
        page_total = len(self.doc) if self.doc else 0
        crop_count = len(self.crop_rects)
        self.status_var.set(f"頁數: {page_num} / {page_total}    已選取裁切區數: {crop_count}")

    def load_pdf(self):
        """載入 PDF 檔案"""
        filepath = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not filepath:
            return
        try:
            doc = fitz.open(filepath)
            if doc.needs_pass:
                if not doc.authenticate("66608251"):  # 預設密碼
                    password = simpledialog.askstring("密碼保護", "此 PDF 受密碼保護，請輸入密碼：", show='*')
                    if not password or not doc.authenticate(password):
                        messagebox.showerror("錯誤", "密碼錯誤或取消，無法開啟 PDF。")
                        return
            self.doc = doc
            self.pdf_path = filepath
            self.current_page_index = 0
            self.crop_rects = []
            self.show_page()
        except Exception as e:
            messagebox.showerror("錯誤", f"開啟 PDF 失敗：{e}")

    def show_page(self):
        """顯示目前頁面並重繪裁切框"""
        if not self.doc:
            return
        page = self.doc.load_page(self.current_page_index)
        zoom_x, zoom_y = self.calculate_zoom_to_fit(page)
        zoom_x *= 0.9
        zoom_y *= 0.9
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom_x, zoom_y))
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.tk_img = ImageTk.PhotoImage(image)
        self.canvas.delete("all")

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        img_width = self.tk_img.width()
        img_height = self.tk_img.height()
        x = max((canvas_width - img_width) // 2, 0)
        y = max((canvas_height - img_height) // 2, 0)
        self.image_offset = (x, y)

        self.canvas.create_image(x, y, image=self.tk_img, anchor=tk.NW)
        self.canvas.config(scrollregion=(0, 0, canvas_width, canvas_height))

        for idx, rect in enumerate(self.crop_rects, start=1):
            x0 = rect[0] * zoom_x + x
            y0 = rect[1] * zoom_y + y
            x1 = rect[2] * zoom_x + x
            y1 = rect[3] * zoom_y + y
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="blue", width=2)
            self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=str(idx), fill="red", font=("Arial", 40, "bold"))

        self.zoom = zoom_x
        self.update_status()

    def calculate_zoom_to_fit(self, page):
        """依照畫布大小自動調整顯示比例"""
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width == 1 or canvas_height == 1:
            return 1.0, 1.0
        page_rect = page.rect
        zoom_x = canvas_width / page_rect.width
        zoom_y = canvas_height / page_rect.height
        zoom = min(zoom_x, zoom_y)
        return zoom, zoom

    def on_mousewheel_zoom(self, event):
        """滑鼠滾輪縮放功能（未實作）"""
        pass

    def start_crop(self, event):
        """滑鼠按下開始選擇裁切區"""
        x = (self.canvas.canvasx(event.x) - self.image_offset[0]) / self.zoom
        y = (self.canvas.canvasy(event.y) - self.image_offset[1]) / self.zoom
        self.start_x = x
        self.start_y = y

    def draw_crop(self, event):
        """滑鼠拖曳選取區域"""
        x = (self.canvas.canvasx(event.x) - self.image_offset[0]) / self.zoom
        y = (self.canvas.canvasy(event.y) - self.image_offset[1]) / self.zoom
        self.canvas.delete("crop")
        self.canvas.create_rectangle(self.start_x * self.zoom + self.image_offset[0],
                                     self.start_y * self.zoom + self.image_offset[1],
                                     x * self.zoom + self.image_offset[0],
                                     y * self.zoom + self.image_offset[1],
                                     outline="red", tag="crop")

    def save_crop(self, event):
        """滑鼠放開後儲存裁切區座標"""
        x = (self.canvas.canvasx(event.x) - self.image_offset[0]) / self.zoom
        y = (self.canvas.canvasy(event.y) - self.image_offset[1]) / self.zoom
        rect = (min(self.start_x, x), min(self.start_y, y),
                max(self.start_x, x), max(self.start_y, y))
        self.crop_rects.append(rect)
        self.show_page()

    def clear_crops(self):
        """清除所有已選裁切區"""
        self.crop_rects.clear()
        self.show_page()

    def undo_crop(self):
        """移除最近新增的裁切區"""
        if self.crop_rects:
            self.crop_rects.pop()
            self.show_page()
        else:
            messagebox.showinfo("提示", "沒有可以返回的裁切區。")

    def export_crops(self):
        """匯出裁切結果成新 PDF"""
        if not self.crop_rects:
            messagebox.showwarning("警告", "尚未選取裁切區域！")
            return

        if not self.pdf_path:
            messagebox.showerror("錯誤", "未開啟任何 PDF 檔案。")
            return

        # 設定流水號
        try:
            self.serial_counter = int(self.serial_start_var.get())
        except Exception:
            messagebox.showerror("錯誤", "起始流水號必須是數字")
            return

        base_dir = os.path.dirname(self.pdf_path)
        pages = range(len(self.doc)) if self.enable_batch.get() else [self.current_page_index]

        output_pdf = fitz.open()
        width_pt = 10 / 2.54 * 72  # 10cm 寬
        height_pt = 15 / 2.54 * 72  # 15cm 高

        img_notice_path = "裁切後加入的圖.jpg"
        if not os.path.exists(img_notice_path):
            messagebox.showerror("錯誤", f"找不到圖片：{img_notice_path}")
            return

        notice_img = fitz.Pixmap(img_notice_path)
        count = 0
        serial_first = self.serial_counter

        for pno in pages:
            page = self.doc.load_page(pno)
            for rect in self.crop_rects:
                crop = fitz.Rect(*rect)
                pix = page.get_pixmap(clip=crop, dpi=300)
                avg_color = sum(pix.samples) / len(pix.samples)
                if avg_color > 250:
                    continue

                img = fitz.Pixmap(pix, 0) if pix.alpha else pix
                new_page = output_pdf.new_page(width=width_pt, height=height_pt)

                # 計算圖片大小與位置（縮小 75% 高度）
                shrink_ratio = 0.75
                target_img_height = height_pt * shrink_ratio
                scale = target_img_height / (img.height * 72 / 300)
                img_width_pt = img.width * 72 / 300 * scale
                img_height_pt = img.height * 72 / 300 * scale

                img_rect = fitz.Rect(0, 0, img_width_pt, img_height_pt)
                x_offset = (width_pt - img_width_pt) / 2
                y_offset = 40
                img_rect.x0 += x_offset
                img_rect.x1 += x_offset
                img_rect.y0 += y_offset
                img_rect.y1 += y_offset
                new_page.insert_image(img_rect, pixmap=img)

                # ===== 流水號 (右上角) =====
                margin = 15
                text = str(self.serial_counter)

                # 在頁面上方建立一個矩形區域，寬度足夠，文字會靠右
                textbox_rect = fitz.Rect(margin, 5, width_pt - margin, 40)

                new_page.insert_textbox(
                textbox_rect,
                text,
                fontsize=20,
                fontname="helv",
                color=(1, 0, 0),
                align=fitz.TEXT_ALIGN_RIGHT   # 這才是正確的寫法
                )
                self.serial_counter += 1


                # ===== 加入底部圖片提示 =====
                max_notice_width = width_pt * 0.8
                scale_n = min(max_notice_width / notice_img.width, 1)
                n_width = notice_img.width * scale_n
                n_height = notice_img.height * scale_n
                n_rect = fitz.Rect(
                    (width_pt - n_width) / 2,
                    height_pt - n_height - 10,
                    (width_pt + n_width) / 2,
                    height_pt - 10
                )
                new_page.insert_image(n_rect, pixmap=notice_img)

                count += 1

        serial_last = self.serial_counter - 1

        try:
            if count == 0:
                messagebox.showinfo("結果", "沒有匯出任何頁面（所有裁切區域皆為空白）")
            else:
                base_name = os.path.splitext(os.path.basename(self.pdf_path))[0]
                save_name = f"{base_name}_已裁切_{serial_first}-{serial_last}.pdf"
                save_path = os.path.join(base_dir, save_name)
                output_pdf.save(save_path)
                messagebox.showinfo("完成", f"已匯出 {count} 頁裁切結果：\n{save_path}")
        except Exception as e:
            messagebox.showerror("錯誤", f"無法儲存檔案：{e}")
        finally:
            output_pdf.close()

    def prev_page(self):
        """切換到上一頁"""
        if self.doc and self.current_page_index > 0:
            self.current_page_index -= 1
            self.crop_rects.clear()
            self.show_page()

    def next_page(self):
        """切換到下一頁"""
        if self.doc and self.current_page_index < len(self.doc) - 1:
            self.current_page_index += 1
            self.crop_rects.clear()
            self.show_page()


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1200x800")
    app = PDFCropper(root)
    root.mainloop()

