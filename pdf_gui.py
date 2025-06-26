import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import threading
import pikepdf
from PIL import Image, ImageTk
import tempfile
import io
import fitz  # PyMuPDF
import pandas as pd
from praser import replace_text, create_tounicode_cmap, parse_cmap, decode_pdf_string
import uuid
import shutil

class PDFReplacerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF-praser")
        self.root.geometry("800x600")
        
        # 当前打开的PDF
        self.current_pdf = None
        self.pdf_document = None
        self.current_page_num = 0
        self.total_pages = 0
        self.original_image = None
        self.preview_pdf = None
        self.zoom_factor = 4
        self.pan_x = 0
        self.pan_y = 0
        self.drag_data = {'x': 0, 'y': 0, 'pan_x': 0, 'pan_y': 0}

        # 存储找到的文本位置
        self.text_positions = []  # 存储 (text, rect) 元组的列表
        self.text_highlights = []  # 存储高亮框的引用
        self.selected_text_instance = None  # 当前选中的文本实例
        
        # 创建主框架
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建左侧控制面板
        self.control_frame = ttk.LabelFrame(self.main_frame, text="edit")
        self.control_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=5, pady=5)
        
        # 创建PDF预览面板
        self.preview_frame = ttk.LabelFrame(self.main_frame, text="Preview")
        self.preview_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 只保留原始PDF预览框
        self.original_frame = ttk.LabelFrame(self.preview_frame, text="PDF")
        self.original_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建原始PDF预览画布，添加滚动条
        self.canvas_scroll_x = tk.Scrollbar(self.original_frame, orient=tk.HORIZONTAL)
        self.canvas_scroll_y = tk.Scrollbar(self.original_frame, orient=tk.VERTICAL)
        self.original_canvas = tk.Canvas(self.original_frame, bg="white",
                                         xscrollcommand=self.canvas_scroll_x.set,
                                         yscrollcommand=self.canvas_scroll_y.set)
        self.canvas_scroll_x.config(command=self.original_canvas.xview)
        self.canvas_scroll_y.config(command=self.original_canvas.yview)

        self.canvas_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.original_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 添加控制元素
        ttk.Label(self.control_frame, text="PDF:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.pdf_path_var = tk.StringVar()
        ttk.Entry(self.control_frame, textvariable=self.pdf_path_var, width=30).grid(row=0, column=1, columnspan=2, padx=5, pady=5)
        ttk.Button(self.control_frame, text="浏览...", command=self.browse_pdf).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(self.control_frame, text="Page:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.page_var = tk.StringVar(value="1")
        self.page_spinbox = ttk.Spinbox(self.control_frame, from_=1, to=1, textvariable=self.page_var, width=5, command=self.page_changed)
        self.page_spinbox.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(self.control_frame, text="/ 0").grid(row=2, column=2, sticky=tk.W, padx=5, pady=5)
        
        ttk.Button(self.control_frame, text="上一页", command=self.prev_page).grid(row=2, column=3, padx=5, pady=5)
        ttk.Button(self.control_frame, text="下一页", command=self.next_page).grid(row=2, column=4, padx=5, pady=5)
        
        ttk.Label(self.control_frame, text="search text:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.find_text_var = tk.StringVar()
        ttk.Entry(self.control_frame, textvariable=self.find_text_var, width=30).grid(row=3, column=1, columnspan=3, padx=5, pady=5)
        ttk.Button(self.control_frame, text="查找", command=self.find_text).grid(row=3, column=4, padx=5, pady=5)
        
        ttk.Label(self.control_frame, text="替换为:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.replace_text_var = tk.StringVar()
        ttk.Entry(self.control_frame, textvariable=self.replace_text_var, width=30).grid(row=4, column=1, columnspan=3, padx=5, pady=5)
        
        ttk.Button(self.control_frame, text="Replace", command=self.execute_replacement).grid(row=5, column=2, padx=5, pady=10)
        ttk.Button(self.control_frame, text="save as", command=self.save_pdf).grid(row=5, column=3, padx=5, pady=10)
        ttk.Button(self.control_frame, text="批量替换", command=self.batch_replace).grid(row=5, column=4, padx=5, pady=10)

        ttk.Button(self.control_frame, text="+", command=self.zoom_in).grid(row=5, column=0, padx=5, pady=10)
        ttk.Button(self.control_frame, text="-", command=self.zoom_out).grid(row=5, column=1, padx=5, pady=10)

        ttk.Label(self.control_frame, text="log:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=5)
        self.log_text = scrolledtext.ScrolledText(self.control_frame, width=40, height=15)
        self.log_text.grid(row=7, column=0, columnspan=5, padx=5, pady=5)
        
        # --- 新增：可替换文本列表 ---
        ttk.Label(self.control_frame, text="可替换文本:").grid(row=8, column=0, sticky=tk.W, padx=5, pady=5)
        self.text_listbox = tk.Listbox(self.control_frame, height=8, width=35)
        self.text_listbox.grid(row=9, column=0, columnspan=5, padx=5, pady=5, sticky=tk.W+tk.E)
        self.text_listbox.bind("<<ListboxSelect>>", self.on_text_selected)
        # ---
        
        # 选择文本实例框架，初始状态为隐藏
        self.instance_frame = ttk.LabelFrame(self.control_frame, text="选择文本实例")
        self.instance_var = tk.StringVar()
        self.instance_listbox = tk.Listbox(self.instance_frame, height=5, width=35)
        self.instance_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.instance_listbox.bind("<<ListboxSelect>>", self.on_instance_selected)
        
        # 添加"替换所有实例"和"仅替换选中实例"按钮
        self.buttons_frame = ttk.Frame(self.instance_frame)
        self.buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(self.buttons_frame, text="替换所有实例", 
                  command=lambda: self.execute_replacement(replace_all=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(self.buttons_frame, text="仅替换选中实例",
                  command=lambda: self.execute_replacement(replace_all=False)).pack(side=tk.RIGHT, padx=5)
        
        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("ready")
        self.status_bar = ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 仅在原始PDF预览画布上绑定窗口大小变化事件
        self.original_canvas.bind("<Configure>", self.on_resize)
        # 启用画布拖动
        self.original_canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.original_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        
        # 缓存 pikepdf 文档，避免每次打开后立即被销毁
        self.pikepdf_doc = None

        # 页面文本解码缓存  page_index -> List[str]
        self.decoded_text_cache = {}
    
    def safe_pikepdf_access(self, obj, key=None, default=None, as_stream=False):
        """
        安全地访问pikepdf对象的属性或方法，避免类型错误
        
        Args:
            obj: pikepdf对象
            key: 要访问的键或属性名
            default: 访问失败时返回的默认值
            as_stream: 是否尝试将对象作为流对象处理
            
        Returns:
            访问结果或默认值
        """
        if obj is None:
            return default
            
        # 尝试解析间接对象 (Indirect Objects)
        try:
            # 若传入的是间接对象包装，则递归解析到真正的底层对象
            # pikepdf.Object 在不同版本中可能需要 get_object() 或 resolve() 获取真实对象
            # 我们在此兼容两种 API，并做最多两级解析以避免潜在的死循环。
            max_depth = 2
            depth = 0
            while isinstance(obj, pikepdf.Object) and depth < max_depth:
                try:
                    if hasattr(obj, "get_object"):
                        obj = obj.get_object()
                    elif hasattr(obj, "resolve"):
                        obj = obj.resolve()
                    else:
                        break
                except Exception:
                    break
                depth += 1
        except Exception:
            # pikepdf 未导入或解析失败时保持原对象
            pass
            
        # 如果没有指定key，则返回对象本身或尝试作为流处理
        if key is None:
            if as_stream and hasattr(obj, 'read_bytes'):
                try:
                    return obj.read_bytes()
                except Exception as e:
                    self.log(f"读取流数据失败: {str(e)}")
                    return default
            return obj
            
        # 处理属性访问
        try:
            # 尝试直接访问属性
            if hasattr(obj, key):
                return getattr(obj, key)
        except Exception:
            pass
            
        # 处理字典式访问
        try:
            if hasattr(obj, '__getitem__'):
                # 如果key是字符串并以'/'开头，先尝试直接访问，再尝试Name对象
                if isinstance(key, str) and key.startswith('/'):
                    # 1) 直接用字符串键
                    try:
                        return obj[key]
                    except Exception:
                        pass
                    # 2) 转为 Name 再访问
                    try:
                        name_key = pikepdf.Name(key[1:])
                        return obj[name_key]
                    except Exception:
                        pass
            else:
                # 非以/开头的key，直接访问
                try:
                    return obj[key]
                except Exception:
                    pass
        except Exception:
            pass

        # 尝试get方法访问
        try:
            if hasattr(obj, 'get'):
                # 对Name对象进行特殊处理
                if isinstance(key, str) and key.startswith('/'):
                    try:
                        name_key = pikepdf.Name(key[1:])
                        return obj.get(name_key, default)
                    except Exception:
                        pass
                return obj.get(key, default)
        except Exception:
            pass

        # 如果是请求作为流处理，尝试读取流数据
        if as_stream and hasattr(obj, 'read_bytes'):
            try:
                return obj.read_bytes()
            except Exception as e:
                self.log(f"读取流数据失败: {str(e)}")

        return default

    def extract_contents_bytes(self, page):
        """
        从页面中提取内容流字节，处理各种特殊情况

        Args:
            page: pikepdf页面对象

        Returns:
            bytes: 内容流字节或None
        """
        if page is None:
            return None

        # 1. 尝试直接使用pikepdf.Page API (注意检查方法是否存在)
        if hasattr(page, 'get_raw_contents'):
            try:
                raw_bytes = page.get_raw_contents()
                if isinstance(raw_bytes, (bytes, bytearray)) and raw_bytes:
                    self.log(f"✅ 使用get_raw_contents()成功获取内容流: {len(raw_bytes)}字节")
                    return bytes(raw_bytes)
            except Exception as e:
                self.log(f"⚠️ get_raw_contents()失败: {str(e)} — 尝试下一种方法")
        elif hasattr(page, 'get_contents'):
            try:
                raw_bytes = page.get_contents()
                if isinstance(raw_bytes, (bytes, bytearray)) and raw_bytes:
                    self.log(f"✅ 使用get_contents()成功获取内容流: {len(raw_bytes)}字节")
                    return bytes(raw_bytes)
            except Exception as e:
                self.log(f"⚠️ get_contents()失败: {str(e)} — 尝试下一种方法")
        else:
            self.log("⚠️ 页面对象没有内容流获取方法 — 尝试直接访问/Contents")

        # 2. 直接尝试访问/Contents键
        try:
            # 直接使用字符串键('/Contents')
            try:
                if '/Contents' in page:
                    contents = page['/Contents']
                    if contents is not None:
                        if isinstance(contents, pikepdf.Array):
                            # 合并数组中的所有流
                            content_bytes = b''
                            for item in contents:
                                try:
                                    item_bytes = self.safe_pikepdf_access(item, as_stream=True)
                                    if item_bytes:
                                        content_bytes += item_bytes
                                except Exception as e:
                                    self.log(f"⚠️ 读取Contents数组项失败: {str(e)}")
                            if content_bytes:
                                self.log(f"✅ 成功合并Contents数组内容: {len(content_bytes)}字节")
                                return content_bytes
                        else:
                            # 单个流对象
                            try:
                                content_bytes = contents.read_bytes()
                                if content_bytes:
                                    self.log(f"✅ 成功读取Contents直接流: {len(content_bytes)}字节")
                                    return content_bytes
                            except Exception as e:
                                self.log(f"⚠️ 读取Contents直接流失败: {str(e)} — 尝试解析间接对象")
                                # 尝试解析间接对象
                                try:
                                    if hasattr(contents, 'get_object'):
                                        resolved = contents.get_object()
                                        if hasattr(resolved, 'read_bytes'):
                                            content_bytes = resolved.read_bytes()
                                            if content_bytes:
                                                self.log(f"✅ 成功读取解析后的Contents流: {len(content_bytes)}字节")
                                                return content_bytes
                                except Exception:
                                    pass
            except Exception as e:
                self.log(f"⚠️ 访问'/Contents'失败: {str(e)}")

            # 尝试不带斜杠的键('Contents')
            try:
                if 'Contents' in page:
                    contents = page['Contents']
                    if contents is not None:
                        if isinstance(contents, pikepdf.Array):
                            content_bytes = b''
                            for item in contents:
                                item_bytes = self.safe_pikepdf_access(item, as_stream=True)
                                if item_bytes:
                                    content_bytes += item_bytes
                            if content_bytes:
                                self.log(f"✅ 通过'Contents'键成功获取内容: {len(content_bytes)}字节")
                                return content_bytes
                        else:
                            content_bytes = self.safe_pikepdf_access(contents, as_stream=True)
                            if content_bytes:
                                self.log(f"✅ 通过'Contents'键成功获取内容: {len(content_bytes)}字节")
                                return content_bytes
            except Exception as e:
                self.log(f"⚠️ 访问'Contents'失败: {str(e)}")

            # 尝试pikepdf.Name对象
            try:
                name_key = pikepdf.Name('Contents')
                if name_key in page:
                    contents = page[name_key]
                    if contents is not None:
                        if isinstance(contents, pikepdf.Array):
                            content_bytes = b''
                            for item in contents:
                                item_bytes = self.safe_pikepdf_access(item, as_stream=True)
                                if item_bytes:
                                    content_bytes += item_bytes
                            if content_bytes:
                                self.log(f"✅ 通过pikepdf.Name('Contents')成功获取内容: {len(content_bytes)}字节")
                                return content_bytes
                        else:
                            content_bytes = self.safe_pikepdf_access(contents, as_stream=True)
                            if content_bytes:
                                self.log(f"✅ 通过pikepdf.Name('Contents')成功获取内容: {len(content_bytes)}字节")
                                return content_bytes
            except Exception as e:
                self.log(f"⚠️ 访问pikepdf.Name('Contents')失败: {str(e)}")

            # 如果到这里还没有找到内容，列出所有键
            try:
                if hasattr(page, 'keys'):
                    keys_list = list(page.keys())
                    self.log(f"⚠️ 页面可用键: {[str(k) for k in keys_list]}")

                    # 搜索可能包含"content"的键（不区分大小写）
                    content_related_keys = []
                    for k in keys_list:
                        key_str = str(k).lower()
                        if 'content' in key_str:
                            content_related_keys.append(str(k))

                    if content_related_keys:
                        self.log(f"📝 发现可能相关的键: {content_related_keys}")
                        # 尝试这些键
                        for k in content_related_keys:
                            try:
                                obj = page.get(pikepdf.Name(k.lstrip('/')))
                                if obj:
                                    if isinstance(obj, pikepdf.Array):
                                        content_bytes = b''
                                        for item in obj:
                                            item_bytes = self.safe_pikepdf_access(item, as_stream=True)
                                            if item_bytes:
                                                content_bytes += item_bytes
                                        if content_bytes:
                                            self.log(f"✅ 通过相关键 {k} 成功获取内容: {len(content_bytes)}字节")
                                            return content_bytes
                                    else:
                                        content_bytes = self.safe_pikepdf_access(obj, as_stream=True)
                                        if content_bytes:
                                            self.log(f"✅ 通过相关键 {k} 成功获取内容: {len(content_bytes)}字节")
                                            return content_bytes
                            except Exception:
                                pass
            except Exception as e:
                self.log(f"⚠️ 搜索可能的内容键失败: {str(e)}")
        except Exception as e:
            self.log(f"⚠️ 直接访问/Contents失败: {str(e)}")

        # 3. 尝试从父对象层次结构继承内容流
        try:
            inherited_contents = self.find_inherited(page, pikepdf.Name('Contents'))
            if inherited_contents is not None:
                if isinstance(inherited_contents, pikepdf.Array):
                    content_bytes = b''
                    for item in inherited_contents:
                        item_bytes = self.safe_pikepdf_access(item, as_stream=True)
                        if item_bytes:
                            content_bytes += item_bytes
                    if content_bytes:
                        self.log(f"✅ 从父对象继承的内容流: {len(content_bytes)}字节")
                        return content_bytes
                else:
                    content_bytes = self.safe_pikepdf_access(inherited_contents, as_stream=True)
                    if content_bytes:
                        self.log(f"✅ 从父对象继承的内容流: {len(content_bytes)}字节")
                        return content_bytes
        except Exception as e:
            self.log(f"⚠️ 从父对象继承/Contents失败: {str(e)}")

        # 4. 最后尝试 PyMuPDF 提取内容流
        try:
            import fitz
            doc = fitz.open(self.current_pdf)
            mupdf_page = doc[self.current_page_num]
            contents = mupdf_page.get_contents()
            if contents:
                xref = contents[0]  # 获取第一个内容流的xref
                raw_content = doc.xref_stream(xref)
                if raw_content:
                    self.log(f"✅ 通过PyMuPDF提取内容流: {len(raw_content)}字节")
                    return raw_content
        except Exception as e:
            self.log(f"⚠️ PyMuPDF提取内容流失败: {str(e)}")

        # 所有方法都失败了
        self.log("❌ 无法获取页面内容流 — 此页面可能不包含可搜索的文本内容")
        return None

    def get_content_bytes(self, page):
        """
        从页面中安全获取内容流字节

        Args:
            page: pikepdf页面对象

        Returns:
            内容流字节或None
        """
        return self.extract_contents_bytes(page)

    def log(self, message):
        """添加日志到日志窗口"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def browse_pdf(self):
        """浏览并选择PDF文件"""
        file_path = filedialog.askopenfilename(
            title="选择PDF文件",
            filetypes=[("PDF文件", "*.pdf"), ("所有文件", "*.*")]
        )
        if file_path:
            self.pdf_path_var.set(file_path)
            self.open_pdf(file_path)

    def open_pdf(self, pdf_path):
        """打开PDF文件并显示第一页"""
        try:
            # 关闭之前的PDF（如果有）
            if self.pdf_document:
                self.pdf_document.close()
            if self.pikepdf_doc:
                try:
                    self.pikepdf_doc.close()
                except Exception:
                    pass
                self.pikepdf_doc = None

            # 清空页面文本缓存
            self.decoded_text_cache.clear()

            # 打开新的PDF文件
            self.pdf_document = fitz.open(pdf_path)
            self.current_pdf = pdf_path
            self.current_page_num = 0
            self.total_pages = len(self.pdf_document)

            # 更新页码范围
            self.page_spinbox.configure(from_=1, to=self.total_pages)
            self.page_var.set("1")

            # 更新页码标签
            for child in self.control_frame.winfo_children():
                if isinstance(child, ttk.Label) and "/ " in child.cget("text"):
                    child.configure(text=f"/ {self.total_pages}")
                    break

            # 显示第一页
            self.show_current_page()

            self.log(f"已打开PDF: {pdf_path}")
            self.log(f"总页数: {self.total_pages}")
            self.status_var.set(f"已打开: {os.path.basename(pdf_path)}")

            # 清除选中的实例
            self.selected_text_instance = None
            self.hide_instance_selector()
        except Exception as e:
            messagebox.showerror("错误", f"无法打开PDF文件: {str(e)}")
            self.log(f"错误: 无法打开PDF文件: {str(e)}")

    def show_current_page(self):
        """显示当前页面，并刷新可替换文本列表"""
        if not self.pdf_document:
            return
        page = self.pdf_document[self.current_page_num]
        self.original_canvas.delete("all")
        # 渲染页面为高分辨率图像
        zoom = self.zoom_factor  # 固定为4
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.original_image = img
        self.tk_image = ImageTk.PhotoImage(image=img)
        self.original_canvas.config(width=img.width, height=img.height)
        self.original_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        # 设置 scrollregion 以支持滚动条
        self.original_canvas.config(scrollregion=(0, 0, img.width, img.height))
        self.status_var.set(f"当前页: {self.current_page_num + 1} / {self.total_pages}  分辨率: {self.zoom_factor}x")
        self.refresh_text_listbox()

        # 清除之前的高亮
        self.text_highlights = []

        # 清除选中的实例
        self.selected_text_instance = None
        self.hide_instance_selector()

    def resize_image(self, img, width, height):
        """调整图像大小以适应指定的宽度和高度，保持纵横比"""
        if width <= 1 or height <= 1:  # 防止除以零错误
            return img

        img_width, img_height = img.size
        ratio = min(width / img_width, height / img_height)
        new_size = (int(img_width * ratio), int(img_height * ratio))
        return img.resize(new_size, Image.LANCZOS)

    def on_resize(self, event):
        if not hasattr(self, 'original_image') or self.original_image is None:
            return

        # 仅当画布尺寸明显变化时才重新渲染图像，避免频繁触发卡顿
        canvas_width = event.width
        canvas_height = event.height
        current_width = self.original_canvas.winfo_width()
        current_height = self.original_canvas.winfo_height()

        if abs(canvas_width - current_width) > 10 or abs(canvas_height - current_height) > 10:
            self.tk_image = ImageTk.PhotoImage(image=self.original_image)
            self.original_canvas.delete("all")
            self.original_canvas.config(scrollregion=(0, 0, self.original_image.width, self.original_image.height))
            self.original_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
            self.original_canvas.image = self.tk_image

            # 重新绘制高亮
            if self.selected_text_instance is not None:
                self.highlight_text_instance(self.selected_text_instance)

    def page_changed(self):
        """页码改变时的处理"""
        if not self.pdf_document:
            return

        try:
            page_num = int(self.page_var.get()) - 1
            if 0 <= page_num < self.total_pages:
                self.current_page_num = page_num
                self.show_current_page()
        except ValueError:
            # 恢复原来的页码
            self.page_var.set(str(self.current_page_num + 1))

    def prev_page(self):
        """显示上一页"""
        if not self.pdf_document or self.current_page_num <= 0:
            return

        self.current_page_num -= 1
        self.page_var.set(str(self.current_page_num + 1))
        self.show_current_page()

    def next_page(self):
        """显示下一页"""
        if not self.pdf_document or self.current_page_num >= self.total_pages - 1:
            return

        self.current_page_num += 1
        self.page_var.set(str(self.current_page_num + 1))
        self.show_current_page()

    def decode_content_stream_text(self, text_content, font_name, page):
        """
        尝试从内容流中解码文本

        Args:
            text_content: 内容流中的原始文本字符串
            font_name: 当前字体名称
            page: PDF页面对象

        Returns:
            解码后的文本
        """
        try:
            # 处理转义字符
            text_content = text_content.replace('\\(', '(').replace('\\)', ')').replace('\\\\', '\\')
            encoded_bytes = text_content.encode("latin1")

            # 默认解码
            decoded_text = encoded_bytes.decode('latin1', errors='replace')

            # 尝试使用CMap进行解码
            try:
                # 先检查page对象是否合法
                if page is None:
                    return decoded_text

                # 获取Resources属性
                resources = self.safe_pikepdf_access(page, 'Resources')
                if resources is None:
                    resources = self.safe_pikepdf_access(page, '/Resources')

                if resources is None:
                    return decoded_text

                # 获取字体字典
                font_dict = self.safe_pikepdf_access(resources, '/Font')
                if font_dict is None:
                    return decoded_text

                # 获取特定字体对象
                font_name_obj = pikepdf.Name(font_name if font_name.startswith('/') else '/' + font_name)

                font_ref = self.safe_pikepdf_access(font_dict, font_name_obj)
                if font_ref is None:
                    # 尝试直接用字符串作为key
                    font_ref = self.safe_pikepdf_access(font_dict, font_name)

                if font_ref is None:
                    return decoded_text

                # 获取ToUnicode映射
                to_unicode = self.safe_pikepdf_access(font_ref, '/ToUnicode')
                if to_unicode is None:
                    return decoded_text

                # 读取CMap流
                cmap_bytes = self.safe_pikepdf_access(to_unicode, as_stream=True)
                if cmap_bytes is None:
                    return decoded_text

                # 导入所需函数并解析CMap
                from praser import parse_cmap, decode_pdf_string

                cmap_str = cmap_bytes.decode('utf-8', errors='ignore')
                cmap = parse_cmap(cmap_str)

                # 使用CMap解码文本
                if cmap:
                    decoded_text = decode_pdf_string(encoded_bytes, cmap)

            except Exception as e:
                self.log(f"CMap解码过程中出错: {str(e)}")
                # 解码失败时使用默认解码结果

            return decoded_text
        except Exception as e:
            self.log(f"文本解码错误: {str(e)}")
            return ""

    def get_pikepdf_page(self, page_index):
        """获取页面的pikepdf对象，用于访问原始内容"""
        try:
            if not self.current_pdf:
                return None

            import pikepdf

            # 1. 若已有缓存且页码有效，直接返回
            try:
                if self.pikepdf_doc is not None:
                    if 0 <= page_index < len(self.pikepdf_doc.pages):
                        return self.pikepdf_doc.pages[page_index]
            except Exception:
                # 缓存可能已失效
                self.pikepdf_doc = None

            # 2. 重新打开并缓存
            try:
                self.pikepdf_doc = pikepdf.open(self.current_pdf)
                if 0 <= page_index < len(self.pikepdf_doc.pages):
                    return self.pikepdf_doc.pages[page_index]
            except Exception as e:
                self.log(f"打开PDF文件时出错: {str(e)}")
                self.pikepdf_doc = None
            return None
        except Exception as e:
            self.log(f"获取pikepdf页面对象失败: {str(e)}")
            return None

    def find_text_instances(self, text_to_find):
        """基于内容流查找文本的所有实例及其位置，支持TJ、Tj和Td操作符"""
        if not self.pdf_document or not text_to_find:
            return []

        instances = []
        page = self.pdf_document[self.current_page_num]
        pikepdf_page = self.get_pikepdf_page(self.current_page_num)

        # ------------------- 首选：PyMuPDF 自带搜索 -------------------
        text_rects = page.search_for(text_to_find, flags=0)  # flags=0 精确匹配大小写

        # 用集合去重（0.1pt 精度）
        seen_keys = set()
        unique_rects = []
        for r in text_rects:
            key = (round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1))
            if key not in seen_keys:
                # 过滤幽灵矩形：宽高过小或落在(0,0)
                if r.width < 1 or r.height < 1 or (r.x0 < 1 and r.y0 < 1):
                    continue
                unique_rects.append(r)
                seen_keys.add(key)

        # 如果已经找到结果，就直接返回，不再解析内容流，避免重复
        if unique_rects:
            for i, rect in enumerate(unique_rects):
                instances.append((f"{text_to_find} (实例 {i+1})", rect, i))
            return instances

        # ------------------- 退回：解析内容流 -------------------
        try:
            # 使用内容流查找文本
            content_bytes = self.get_content_bytes(pikepdf_page)
            if not content_bytes:
                self.log("页面不包含内容流")
                raise ValueError("页面不包含内容流")

            content_str = content_bytes.decode('latin1', errors='replace')

            # 使用正则表达式查找文本对象 (Tj、Tj操作符)和位置操作符(Td)
            import re
            text_pattern = re.compile(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]')
            font_pattern = re.compile(r'/([A-Za-z0-9]+)\s+\d+\s+Tf')
            matrix_pattern = re.compile(r'(?:[-\d.]+\s+){5}[-\d.]+\s+Tm')
            td_pattern = re.compile(r'([-\d.]+)\s+([-\d.]+)\s+Td')  # 匹配Td操作符及其参数

            current_font = None
            current_pos = (0, 0)  # 默认位置
            found_positions = []
            # 统一去重容器，后面 PyMuPDF 也会继续复用
            seen_keys = set()

            # 遍历内容流中的所有文本对象和位置操作符（仅当 search_for 未找到时才执行）
            for match in re.finditer(
                    r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf|(?:[-\d.]+\s+){5}[-\d.]+\s+Tm|(?:[-\d.]+)\s+(?:[-\d.]+)\s+Td',
                    content_str):

                # 处理字体切换
                font_match = font_pattern.search(match.group(0))
                if font_match:
                    current_font = '/' + font_match.group(1)
                    continue

                # 处理矩阵变换 (位置信息)
                matrix_match = matrix_pattern.search(match.group(0))
                if matrix_match:
                    # 从矩阵中提取位置信息 (最后两个参数是 x,y 位置)
                    matrix_parts = matrix_match.group(0).strip().split()
                    if len(matrix_parts) >= 6:
                        try:
                            x, y = float(matrix_parts[-2]), float(matrix_parts[-1])
                            current_pos = (x, y)
                        except ValueError:
                            pass
                    continue

                # 处理Td操作符 (相对位置移动)
                td_match = td_pattern.search(match.group(0))
                if td_match:
                    try:
                        dx, dy = float(td_match.group(1)), float(td_match.group(2))
                        x, y = current_pos
                        # 更新当前位置
                        current_pos = (x + dx, y + dy)
                    except ValueError:
                        pass
                    continue

                # 处理文本对象
                text_match = text_pattern.search(match.group(0))
                if text_match and current_font:
                    is_tj = match.group(0).strip().endswith('TJ')
                    inner_text = text_match.group(2) if is_tj else text_match.group(1)

                    # 如果是TJ操作符，需要处理可能的数组格式
                    if is_tj:
                        # 提取TJ数组内的实际文本，忽略间距调整值
                        try:
                            processed_text = ""
                            parts = inner_text.split()
                            for part in parts:
                                if part.startswith('(') and part.endswith(')'):
                                    # 这是文本部分
                                    text_part = part[1:-1]
                                    processed_text += text_part
                            if processed_text:
                                inner_text = processed_text
                        except Exception as e:
                            self.log(f"处理TJ数组时出错: {str(e)}")

                    # 使用专用方法解码文本
                    decoded_text = self.decode_content_stream_text(inner_text, current_font, pikepdf_page)

                    # 检查解码后的文本是否包含目标文本
                    if text_to_find in decoded_text:
                        # 找到匹配的文本，计算在页面中的大致位置
                        # 计算目标文本在解码文本中的起始位置
                        start_pos = decoded_text.find(text_to_find)
                        # 获取当前文本在页面的坐标点
                        x0, y0 = current_pos

                        # 估算字体大小和文本宽度 (在没有真实字体信息的情况下)
                        font_size = 12  # 假设字体大小为12点
                        char_width = 8   # 假设每个字符宽8点

                        # 计算起始偏移和文本宽度
                        offset = start_pos * char_width
                        text_width = len(text_to_find) * char_width
                        text_height = font_size * 1.2  # 行高通常比字体大一些

                        # 将 PDF 坐标(左下原点) 转为 PyMuPDF 坐标(左上原点)
                        zoom = self.zoom_factor
                        x0 = current_pos[0] * zoom
                        y0 = current_pos[1] * zoom
                        x1 = x0 + text_width
                        y1 = y0 + text_height

                        # 创建 fitz.Rect 对象 (x0, y0, x1, y1) 以左上为原点
                        import fitz
                        rect = fitz.Rect(x0, y0, x1, y1)

                        # 过滤掉疑似幽灵位置 (0,0)
                        if x0 == 0 and y0 == 0:
                            continue

                        # 保存实例位置信息（先做去重）
                        key = (round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2))
                        if key not in seen_keys:
                            found_positions.append((text_to_find, rect))
                            seen_keys.add(key)

            # 将内容流结果加入实例列表
            for i, (text, rect) in enumerate(found_positions):
                instances.append((f"{text} (实例 {i+1})", rect, i))

        except Exception as e:
            self.log(f"基于内容流查找文本时出错: {str(e)}")

        return instances

    def find_text(self, auto_select_first=True):
        """查找文本

        Args:
            auto_select_first: 是否自动选择第一个实例，从左边列表选择文本时应设为False
        """
        if not self.pdf_document:
            messagebox.showinfo("提示", "请先打开PDF文件")
            return

        text_to_find = self.find_text_var.get()
        if not text_to_find:
            self.log("请输入要查找的文本")
            return

        self.log(f"正在查找文本: '{text_to_find}'")

        # 在当前页面查找文本和位置
        text_instances = self.find_text_instances(text_to_find)

        if text_instances:
            self.text_positions = text_instances
            instance_count = len(text_instances)
            self.log(f"在第 {self.current_page_num + 1} 页找到 {instance_count} 个 '{text_to_find}' 的实例")

            # 显示选择实例界面
            self.show_instance_selector(text_instances)
            if auto_select_first and instance_count > 0:
                # 自动选择第一个实例并高亮显示
                self.selected_text_instance = text_instances[0]
                self.highlight_text_instance(text_instances[0])
                self.instance_listbox.selection_set(0)  # 让列表显示选中第一项
            # messagebox.showinfo("查找结果", f"在当前页面找到 {instance_count} 个文本: '{text_to_find}'")
        else:
            self.log(f"在第 {self.current_page_num + 1} 页未找到文本: '{text_to_find}'")
            self.selected_text_instance = None
            self.hide_instance_selector()

            # 询问是否要在所有页面中查找
            if messagebox.askyesno("查找", "在当前页面未找到文本，是否要在所有页面中查找？"):
                self.find_text_in_all_pages(text_to_find)

    def show_instance_selector(self, instances):
        """显示文本实例选择器"""
        # 清空并填充实例列表
        self.instance_listbox.delete(0, tk.END)
        for inst_text, rect, index in instances:
            self.instance_listbox.insert(tk.END, inst_text)

        # 显示实例选择器框架
        self.instance_frame.grid(row=10, column=0, columnspan=5, padx=5, pady=5, sticky=tk.W+tk.E)

    def hide_instance_selector(self):
        """隐藏文本实例选择器"""
        self.instance_frame.grid_forget()

    def on_instance_selected(self, event):
        """当用户选择文本实例时"""
        selection = self.instance_listbox.curselection()
        if selection and self.text_positions:
            index = selection[0]
            if 0 <= index < len(self.text_positions):  # 确保索引在有效范围内
                self.selected_text_instance = self.text_positions[index]
                self.highlight_text_instance(self.selected_text_instance)
                self.log(f"选中实例 {index+1}")
            else:
                self.log(f"警告：选中的实例索引 {index} 超出范围（总实例数：{len(self.text_positions)}）")

    def highlight_text_instance(self, instance):
        """高亮显示选中的文本实例"""
        # 清除现有高亮
        for rect_id in self.text_highlights:
            self.original_canvas.delete(rect_id)
        self.text_highlights = []

        # 获取文本矩形坐标
        _, rect, _ = instance

        # 将 PDF 坐标(左下原点) 转为 PyMuPDF 坐标(左上原点)
        zoom = self.zoom_factor
        x0 = rect.x0 * zoom
        y0 = rect.y0 * zoom
        x1 = rect.x1 * zoom
        y1 = rect.y1 * zoom

        # 仅绘制红色边框，不填充
        rect_id = self.original_canvas.create_rectangle(
            x0, y0, x1, y1,
            outline="red",
            width=2
        )

        self.text_highlights.append(rect_id)

        # 确保文本在可视区域中央
        # 计算滚动位置来居中显示选中文本
        canvas_width = self.original_canvas.winfo_width()
        canvas_height = self.original_canvas.winfo_height()

        # 计算滚动到的位置（保持矩形中心）
        scroll_x = max(0, (x0 + x1) / 2 - canvas_width / 2)
        scroll_y = max(0, (y0 + y1) / 2 - canvas_height / 2)

        # 设置画布的滚动位置
        if hasattr(self, 'original_image') and self.original_image:
            # 安全地设置滚动位置
            try:
                self.original_canvas.xview_moveto(scroll_x / self.original_image.width)
                self.original_canvas.yview_moveto(scroll_y / self.original_image.height)
            except Exception as e:
                self.log(f"滚动到高亮区域时出错: {str(e)}")
                # 备用方案：确保矩形在可视区域
                self.original_canvas.update_idletasks()
                self.original_canvas.xview_moveto(max(0, min(1.0, x0 / self.original_image.width - 0.1)))
                self.original_canvas.yview_moveto(max(0, min(1.0, y0 / self.original_image.height - 0.1)))

    def find_text_in_all_pages(self, text_to_find):
        """在所有页面中查找文本"""
        found_pages = []

        for i in range(self.total_pages):
            page = self.pdf_document[i]
            text = page.get_text()

            if text_to_find in text:
                found_pages.append(i + 1)

        if found_pages:
            pages_str = ", ".join(map(str, found_pages))
            self.log(f"在以下页面找到文本 '{text_to_find}': {pages_str}")

            # 询问是否要跳转到第一个找到的页面
            if messagebox.askyesno("查找结果", f"在以下页面找到文本 '{text_to_find}': {pages_str}\n\n是否要跳转到第一个找到的页面？"):
                self.current_page_num = found_pages[0] - 1
                self.page_var.set(str(self.current_page_num + 1))
                self.show_current_page()
                # 跳转后再次在当前页面查找，以高亮显示
                self.find_text(auto_select_first=False)
        else:
            self.log(f"在所有页面中未找到文本: '{text_to_find}'")
            messagebox.showinfo("查找结果", f"在所有页面中未找到文本: '{text_to_find}'")

    def execute_replacement(self, replace_all=False):
        """执行替换操作"""
        if not self.pdf_document:
            messagebox.showinfo("提示", "请先打开PDF文件")
            return

        target_text = self.find_text_var.get()
        replacement_text = self.replace_text_var.get()

        if not target_text:
            messagebox.showinfo("提示", "请输入要查找的文本")
            return

        if not replacement_text:
            messagebox.showinfo("提示", "请输入替换文本")
            return

        # 确定实例索引（如果要替换特定实例）
        instance_index = -1
        if not replace_all and self.selected_text_instance:
            _, _, instance_index = self.selected_text_instance

        # 确认是否替换
        if replace_all:
            confirm_msg = f"确定要替换所有 '{target_text}' 为 '{replacement_text}'?"
        else:
            if instance_index >= 0:
                confirm_msg = f"确定要替换选中的 '{target_text}' 实例为 '{replacement_text}'?"
            else:
                confirm_msg = f"未选择特定实例。确定要替换所有 '{target_text}' 为 '{replacement_text}'?"
                replace_all = True  # 如果没有选择特定实例，默认替换所有

        if not messagebox.askyesno("确认", confirm_msg):
            return

        # 设置输出路径
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.basename(self.current_pdf)
        output_pdf = os.path.join(output_dir, f"replaced_{base_name}")

        # 在新线程中执行替换
        self.status_var.set("正在替换...")
        self.root.update()

        threading.Thread(target=self._execute_replacement,
                         args=(target_text, replacement_text, output_pdf, instance_index)).start()

    def _execute_replacement(self, target_text, replacement_text, output_pdf, instance_index=-1):
        """在新线程中执行替换"""
        try:
            # 检查替换文本中是否包含原始PDF中不存在的字符
            unsupported_chars = self.check_unsupported_chars(replacement_text, target_text)
            if unsupported_chars:
                # 弹窗确认是否继续
                unsupported_chars_str = ''.join(unsupported_chars)
                msg = (
                    f"替换文本中包含目标字体不支持的字符: '{unsupported_chars_str}'\n"
                    f"这些字符将被跳过或可能显示为占位符。是否继续？"
                )
                if not messagebox.askyesno("警告", msg):
                    self.log("替换已取消")
                    self.root.after(0, lambda: self.status_var.set("替换已取消"))
                    return

                self.log(f"⚠️ 替换文本中包含目标字体不支持的字符: '{unsupported_chars_str}'")

            # 计算实际写入PDF的替换文本（去除不支持字符）
            filtered_replacement_text = replacement_text
            if unsupported_chars:
                filtered_replacement_text = ''.join([c for c in replacement_text if c not in unsupported_chars])

            # 调用替换函数
            self.log(f"执行替换: '{target_text}' -> '{filtered_replacement_text}'")
            self.log(f"在第 {self.current_page_num + 1} 页")

            replace_text(
                input_pdf=self.current_pdf,
                output_pdf=output_pdf,
                target_text=target_text,
                replacement_text=filtered_replacement_text,
                page_num=self.current_page_num,
                ttf_file=None,
                instance_index=instance_index  # 传递实例索引
            )

            # 检查文件是否创建成功
            if os.path.exists(output_pdf):
                self.log(f"替换成功，文件保存为: {output_pdf}")

                # 若存在不支持字符，则在输出 PDF 中进行标记
                if unsupported_chars:
                    try:
                        # 若有选中实例，取其矩形
                        selected_rect = None
                        if self.selected_text_instance is not None:
                            selected_rect = self.selected_text_instance[1]

                        self.mark_unsupported_characters(
                            pdf_path=output_pdf,
                            page_index=self.current_page_num,
                            unsupported_chars=unsupported_chars,
                            replacement_text=filtered_replacement_text,
                            target_text=target_text,
                            instance_rect=selected_rect
                        )
                        self.log("已在 PDF 中标记不支持字符的位置")
                    except Exception as e:
                        self.log(f"标记不支持字符时出错: {e}")

                self.root.after(0, lambda: self.status_var.set(f"替换成功，文件保存为: {os.path.basename(output_pdf)}"))

                # 询问是否打开新文件
                if messagebox.askyesno("替换完成", f"替换成功，文件保存为: {output_pdf}\n\n是否打开新文件？"):
                    self.root.after(0, lambda: self.open_pdf(output_pdf))
            else:
                self.log("替换失败")
                self.root.after(0, lambda: self.status_var.set("替换失败"))

            # 读取替换日志中的警告信息并提示
            try:
                self._show_replace_warnings()
            except Exception:
                pass

        except Exception as e:
            err_msg = str(e)
            self.log(f"替换错误: {err_msg}")
            # 使用默认参数把字符串绑定到 lambda，避免 e 超出作用域后被清理导致 NameError
            self.root.after(0, lambda m=err_msg: self.status_var.set("替换错误: " + m))
            self.root.after(0, lambda m=err_msg: messagebox.showerror("错误", f"替换过程中发生错误: {m}"))

    def check_unsupported_chars(self, text, target_text=None):
        """检查文本中是否包含当前字体中不存在的字符

        Args:
            text (str): 待检查的替换文本
            target_text (str, optional): 原始目标文本，用于定位字体；若为空则回退到界面输入框
        """
        if target_text is None:
            # 若批量流程未设置 find_text_var，则使用传入值
            try:
                target_text = self.find_text_var.get()
            except Exception:
                target_text = ""

        if not self.pdf_document or not text:
            return []

        # 获取当前页面
        page = self.pdf_document[self.current_page_num]

        # 获取页面中的文本及其对应的字体信息，使用PyMuPDF的内部机制
        blocks = page.get_text("dict")["blocks"]
        font_chars = {}  # 字体名称 -> 该字体包含的字符集

        # 从当前页面的文本块中收集每个字体包含的字符

        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        font_name = span["font"]
                        text_content = span["text"]
                        if font_name not in font_chars:
                            font_chars[font_name] = set()
                        font_chars[font_name].update(text_content)

        if not font_chars:
            # 如果无法获取字体信息，回退到检查所有文本
            all_pdf_text = page.get_text()
            unsupported = []
            for char in text:
                if char not in all_pdf_text and char not in " \t\n\r":
                    unsupported.append(char)
            return unsupported

        # 获取要替换的文本所使用的字体
        target_font = None

        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        if target_text in span["text"]:
                            target_font = span["font"]
                            break
                    if target_font:
                        break
                if target_font:
                    break

        # 如果找不到目标文本的字体，检查所有字体
        if not target_font:
            all_chars = set()
            for chars in font_chars.values():
                all_chars.update(chars)

            unsupported = []
            for char in text:
                if char not in all_chars and char not in " \t\n\r":
                    unsupported.append(char)
            return unsupported

        # 只检查目标文本字体中包含的字符
        target_font_chars = font_chars.get(target_font, set())
        unsupported = []
        for char in text:
            if char not in target_font_chars and char not in " \t\n\r":
                unsupported.append(char)

        self.log(f"使用字体: {target_font} 检查替换文本字符")
        return unsupported

    def save_pdf(self):
        """保存修改后的PDF（提示用户先执行替换）"""
        if not os.path.exists("output") or not any(f.endswith('.pdf') for f in os.listdir("output")):
            messagebox.showinfo("提示", "请先执行替换操作")
            return
        output_pdf = filedialog.asksaveasfilename(
            title="保存PDF文件",
            defaultextension=".pdf",
            filetypes=[("PDF文件", "*.pdf"), ("所有文件", "*.*")]
        )
        if not output_pdf:
            return
        # 找到最新的replaced_*.pdf
        pdfs = [f for f in os.listdir("output") if f.startswith("replaced_") and f.endswith(".pdf")]
        if not pdfs:
            messagebox.showinfo("提示", "没有可保存的替换结果，请先执行替换操作")
            return
        latest_pdf = max(pdfs, key=lambda f: os.path.getmtime(os.path.join("output", f)))
        try:
            shutil.copy2(os.path.join("output", latest_pdf), output_pdf)
            self.log(f"文件已保存为: {output_pdf}")
            self.status_var.set(f"文件已保存为: {os.path.basename(output_pdf)}")
            messagebox.showinfo("保存成功", f"文件已保存为: {output_pdf}")
        except Exception as e:
            self.log(f"保存错误: {str(e)}")
            self.status_var.set("保存错误")
            messagebox.showerror("错误", f"保存过程中发生错误: {str(e)}")

    def on_text_selected(self, event):
        """当用户选择文本列表中的文本时"""
        selection = self.text_listbox.curselection()
        if selection:
            value = self.text_listbox.get(selection[0])
            self.find_text_var.set(value)
            # 查找并高亮所选文本，但暂不自动点击第一个实例
            self.find_text(auto_select_first=False)
            self.selected_text_instance = None  # 清除先前选中的实例
            # self.hide_instance_selector()       # 确保实例选择器关闭

    def safe_bytes_from_str(self, raw):
        try:
            b = raw.encode('latin1')
            if all(0 <= x < 256 for x in b):
                return b
        except Exception:
            pass
        return None

    def safe_bytes_from_hex(self, hexstr):
        try:
            b = bytes.fromhex(hexstr)
            if all(0 <= x < 256 for x in b):
                return b
        except Exception:
            pass
        return None

    def collect_decoded_texts(self, page_index):
        """收集指定页面全部可解码的文本段落
        返回 List[(font_name, decoded_text, encoded_bytes)]"""
        # 若缓存已存在直接返回
        if page_index in self.decoded_text_cache:
            return self.decoded_text_cache[page_index]

        results = []
        try:
            pikepdf_page = self.get_pikepdf_page(page_index)
            if pikepdf_page is None:
                return results
            # 1. 准备字体 CMap
            font_cmaps = {}
            resources = self.safe_pikepdf_access(pikepdf_page, '/Resources')
            if resources is None:
                return results
            font_dict = self.safe_pikepdf_access(resources, '/Font')
            if font_dict is None:
                return results
            # 遍历字体，确保都有 ToUnicode
            for font_name_obj, font_ref in font_dict.items():
                font_name = str(font_name_obj)
                cmap = None
                if '/ToUnicode' in font_ref:
                    try:
                        cmap_bytes = font_ref['/ToUnicode'].read_bytes()
                        cmap_str = cmap_bytes.decode('utf-8', errors='ignore')
                        cmap = parse_cmap(cmap_str)
                    except Exception:
                        pass
                else:
                    # 动态创建一个基础 WinAnsiEncoding CMap（仅本地使用，不写回 PDF）
                    try:
                        cmap_str = create_tounicode_cmap(font_ref)
                        cmap = parse_cmap(cmap_str)
                    except Exception:
                        pass
                if cmap:
                    font_cmaps[font_name] = cmap
            # 2. 解析内容流
            content_bytes = self.get_content_bytes(pikepdf_page)
            if not content_bytes:
                return results
            content_str = content_bytes.decode('latin1', errors='replace')
            import re
            text_pattern = re.compile(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]')
            font_pattern = re.compile(r'/([A-Za-z0-9]+)\s+\d+\s+Tf')
            current_font = None
            for match in re.finditer(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf', content_str):
                font_match = font_pattern.search(match.group(0))
                if font_match:
                    current_font = '/' + font_match.group(1)
                    continue
                text_match = text_pattern.search(match.group(0))
                if text_match and current_font in font_cmaps:
                    is_tj = match.group(0).strip().endswith('TJ')
                    inner_text = text_match.group(2) if is_tj else text_match.group(1)
                    # 处理 TJ 数组
                    if is_tj:
                        try:
                            processed = ''
                            for part in inner_text.split():
                                if part.startswith('(') and part.endswith(')'):
                                    processed += part[1:-1]
                            if processed:
                                inner_text = processed
                        except Exception:
                            pass
                    # 转义还原
                    try:
                        inner_text_clean = inner_text.replace('\\(', '(').replace('\\)', ')').replace('\\\\', '\\')
                        encoded = inner_text_clean.encode('latin1')
                        decoded = decode_pdf_string(encoded, font_cmaps[current_font])
                        if decoded:
                            results.append((current_font, decoded.strip(), encoded))
                    except Exception:
                        pass
        except Exception as e:
            self.log(f"collect_decoded_texts 错误: {e}")
        # 将解码后的纯文本缓存下来，便于后续快速加载
        self.decoded_text_cache[page_index] = results
        return results

    def refresh_text_listbox(self):
        """基于内容流提取当前页全部可解析文本，填充列表框"""
        self.text_listbox.delete(0, tk.END)
        if not self.pdf_document:
            return

        decoded_items = self.collect_decoded_texts(self.current_page_num)
        found_set = set()
        # 直接将解码文本加入列表（去重），避免再次调用 find_text_instances 造成重复解析
        for _, text_str, _ in decoded_items:
            if text_str and text_str not in found_set:
                self.text_listbox.insert(tk.END, text_str)
                found_set.add(text_str)

        # 若未找到任何文本，回退到 PyMuPDF
        if not self.text_listbox.size():
            try:
                page = self.pdf_document[self.current_page_num]
                all_text = page.get_text()
                for line in all_text.splitlines():
                    line = line.strip()
                    if not line or line in found_set:
                        continue
                    try:
                        instances = self.find_text_instances(line)
                    except Exception:
                        instances = []
                    if instances:
                        self.text_listbox.insert(tk.END, line)
                        found_set.add(line)
            except Exception as e:
                self.log(f"PyMuPDF 提取文本失败: {e}")

    def on_canvas_press(self, event):
        self.drag_data['x'] = event.x
        self.drag_data['y'] = event.y

    def on_canvas_drag(self, event):
        dx = self.drag_data['x'] - event.x
        dy = self.drag_data['y'] - event.y

        # 限制拖动速度（每次最大移动 5 像素）
        dx = max(-1, min(1, dx))
        dy = max(-1, min(1, dy))

        # 执行滚动
        self.original_canvas.xview_scroll(int(dx), "units")
        self.original_canvas.yview_scroll(int(dy), "units")

        self.drag_data['x'] = event.x
        self.drag_data['y'] = event.y

    def on_canvas_release(self, event):
        pass

    def zoom_in(self):
        if self.zoom_factor < 10:
            self.zoom_factor += 1
            self.show_current_page()

    def zoom_out(self):
        if self.zoom_factor > 1:
            self.zoom_factor -= 1
            self.show_current_page()

    def find_inherited(self, page, key):
        p = page
        while p is not None:
            if key in p.obj:
                return p.obj[key]
            p = p.obj.get('/Parent', None)
        return None

    def mark_unsupported_characters(self, pdf_path, page_index, unsupported_chars, replacement_text=None, target_text=None, instance_rect=None, target_font=None):
        """在指定页面标记不支持字符或替换文本位置。

        若页面中找不到不支持字符，则尝试标记替换文本的位置；如果仍未找到，则退回到原始目标文本。

        Args:
            pdf_path (str): PDF 路径
            page_index (int): 页码索引（0 基）
            unsupported_chars (List[str]): 不支持字符列表
            replacement_text (str, optional): 替换后的文本
            target_text (str, optional): 原始待替换文本
            instance_rect (fitz.Rect, optional): 选中实例的矩形
        """
        if not unsupported_chars:
            return

        import fitz

        try:
            doc = fitz.open(pdf_path)
            if page_index < 0 or page_index >= len(doc):
                doc.close()
                return

            page = doc[page_index]

            # 注释内容
            note_content = f"Unsupported chars: {''.join(unsupported_chars)}"

            def add_annots(rects):
                if not rects:
                    return
                self.log(f"📍 标记 {len(rects)} 处可能含不支持字符的位置")
                for rect in rects:
                    try:
                        # 使用矩形批注 + 高亮，使读者更易察觉
                        annot = page.add_rect_annot(rect)
                        annot.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))  # 红边+淡红填充
                        annot.set_opacity(0.15)
                        annot.set_border(width=2)
                        annot.set_info({"title": "PDF-praser", "content": note_content})
                        annot.update()
                    except Exception as ee:
                        # 若矩形批注失败则退回高亮
                        try:
                            quad = [rect.x0, rect.y1, rect.x1, rect.y1, rect.x0, rect.y0, rect.x1, rect.y0]
                            annot = page.add_highlight_annot(quad)
                            annot.set_colors(stroke=(1, 0, 0))
                            annot.set_opacity(0.3)
                            annot.update()
                        except Exception:
                            pass

            found_any = False

            # 0) 若传入显式矩形，则直接标注
            if instance_rect is not None:
                if isinstance(instance_rect, (list, tuple)):
                    add_annots(instance_rect)
                else:
                    add_annots([instance_rect])
                found_any = True

            # 1) 优先查找替换后的整段文本，避免过度标记
            if not found_any and replacement_text:
                rects = page.search_for(replacement_text, flags=0)
                if rects:
                    add_annots(rects)
                    found_any = True

            # 2) 若未找到，则回退到原始目标文本
            if not found_any and target_text:
                rects = page.search_for(target_text, flags=0)
                if rects:
                    add_annots(rects)
                    found_any = True

            # 3) 最后才逐字符查找不支持字符，这一步可能产生较多匹配，因此放在末尾并加以限制
            if not found_any:
                for ch in unsupported_chars:
                    if ch.isspace():
                        continue
                    rects = page.search_for(ch, flags=0)
                    if rects:
                        add_annots(rects)
                        found_any = True

            # 4) 若仍未找到，尝试在文本块中精准匹配
            if not found_any:
                try:
                    text_dict = page.get_text("dict")
                    candidate_rects = []
                    for block in text_dict.get("blocks", []):
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                span_text = span.get("text", "")
                                span_font = span.get("font", "")
                                if target_font and span_font != target_font:
                                    continue
                                if any(ch in span_text for ch in unsupported_chars):
                                    rect = fitz.Rect(span["bbox"])
                                    candidate_rects.append(rect)
                                elif replacement_text and replacement_text in span_text:
                                    rect = fitz.Rect(span["bbox"])
                                    candidate_rects.append(rect)
                                elif target_text and target_text in span_text:
                                    rect = fitz.Rect(span["bbox"])
                                    candidate_rects.append(rect)
                    if candidate_rects:
                        add_annots(candidate_rects)
                        found_any = True
                except Exception:
                    pass

            if found_any:
                doc.save(pdf_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
            doc.close()
        except Exception as e:
            raise e

    # ---------------- 批量替换 ----------------
    def batch_replace(self):
        """从 Excel 表批量生成多个 PDF"""
        if not self.pdf_document:
            messagebox.showinfo("提示", "请先打开模板 PDF 文件")
            return

        excel_path = filedialog.askopenfilename(
            title="选择 Excel 文件",
            filetypes=[("Excel 文件", "*.xlsx *.xls"), ("所有文件", "*.*")]
        )
        if not excel_path:
            return

        # 在新线程中执行耗时任务
        self.status_var.set("批量替换进行中...")
        threading.Thread(target=self._batch_replace_thread, args=(excel_path,)).start()

    def _batch_replace_thread(self, excel_path):
        try:
            self.log(f"读取 Excel: {excel_path}")
            df = pd.read_excel(excel_path, header=None)
            if df.shape[1] < 2:
                self.log("Excel 至少需要两列：第一列模板文本，其余列为替换文本")
                return

            # 第一列是模板文本
            template_texts = df.iloc[:, 0].astype(str).tolist()

            template_pdf = self.current_pdf
            if not template_pdf:
                self.log("未找到当前 PDF")
                return

            output_dir = "output"
            os.makedirs(output_dir, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(template_pdf))[0]

            for col_idx in range(1, df.shape[1]):
                replacement_texts = df.iloc[:, col_idx].astype(str).tolist()
                # 生成输出文件名，取该列第一行非空内容作为标识
                col_tag = replacement_texts[0] if replacement_texts[0] else f"col{col_idx}"
                safe_tag = ''.join(ch for ch in col_tag if ch.isalnum() or ch in ('_', '-'))
                output_pdf = os.path.join(output_dir, f"{base_name}_{safe_tag}.pdf")

                # 先复制模板作为起始文件
                shutil.copy2(template_pdf, output_pdf)

                current_pdf_path = output_pdf

                self.log(f"\n▶ 开始生成: {output_pdf}")

                # 逐条替换
                for idx, (target_text, repl_text) in enumerate(zip(template_texts, replacement_texts)):
                    if not target_text or not repl_text:
                        continue
                    # 每次替换写到唯一临时文件再覆盖
                    tmp_path = os.path.join(output_dir, f"_tmp_{uuid.uuid4().hex}.pdf")
                    try:
                        # 检查替换文本是否包含未映射字符
                        unsupported_chars = self.check_unsupported_chars(str(repl_text), target_text=str(target_text))
                        replace_text(
                            input_pdf=current_pdf_path,
                            output_pdf=tmp_path,
                            target_text=str(target_text),
                            replacement_text=str(repl_text),
                            page_num=0,
                            ttf_file=None,
                            instance_index=-1
                        )
                        # 替换完成后覆盖当前文件（仅当生成文件存在）
                        if os.path.exists(tmp_path):
                            shutil.move(tmp_path, current_pdf_path)
                            self.log(f"   • 替换 {target_text} → {repl_text}")

                            # 如果存在不支持字符，进行标记
                            if unsupported_chars:
                                try:
                                    # 获取目标字体名称
                                    try:
                                        fitz_doc = fitz.open(current_pdf_path)
                                        p0 = fitz_doc[0]
                                        target_font_name = self.get_font_for_text(p0, str(target_text))
                                        fitz_doc.close()
                                    except Exception:
                                        target_font_name = None
                                    # 在替换前获取目标文本在页面中的矩形位置
                                    try:
                                        doc_before = fitz.open(current_pdf_path)
                                        page_before = doc_before[0]
                                        target_rects = page_before.search_for(str(target_text), flags=0)
                                        doc_before.close()
                                    except Exception:
                                        target_rects = []
                                    self.mark_unsupported_characters(
                                        pdf_path=current_pdf_path,
                                        page_index=0,
                                        unsupported_chars=unsupported_chars,
                                        replacement_text=str(repl_text),
                                        target_text=str(target_text),
                                        instance_rect=target_rects,
                                        target_font=target_font_name
                                    )
                                except Exception as me:
                                    self.log(f"   ⚠️ 标记不支持字符失败: {me}")
                        else:
                            self.log(f"⚠️ 未生成输出文件，可能未找到目标文本 '{target_text}'，已跳过此替换")
                    except Exception as e:
                        self.log(f"⚠️ 执行替换时出错 ({target_text}): {e}")
                        # 清理 tmp
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass

                self.log(f"✅ 生成完成: {output_pdf}")

            self.root.after(0, lambda: self.status_var.set("批量替换完成"))

        except Exception as e:
            err = str(e)
            self.log(f"批量替换错误: {err}")
            self.root.after(0, lambda: self.status_var.set("批量替换错误"))

    def get_font_for_text(self, page, search_text):
        """返回页面中包含 search_text 的第一处 span 的字体名，如找不到则返回 None"""
        try:
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if search_text in span.get("text", ""):
                            return span.get("font")
        except Exception:
            pass
        return None

    def _show_replace_warnings(self):
        """读取最新 output/replace_log.txt，若包含关键警告则弹窗提示"""
        log_path = os.path.join("output", "replace_log.txt")
        if not os.path.exists(log_path):
            return
        warnings = []
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                keywords = [
                    "替换文本包含当前字体中不存在的字符",
                    "已过滤不支持的字符",
                    "无法确定目标文本使用的字体",
                    "替换所有实例",
                    "🧾",
                ]
                for line in f.readlines():
                    txt = line.strip()
                    if any(kw in txt for kw in keywords):
                        warnings.append(txt)
        except Exception:
            return
        if warnings:
            def _popup(msg):
                messagebox.showinfo("替换警告", msg)
            self.root.after(0, _popup, "\n".join(warnings))


if __name__ == "__main__":
    root = tk.Tk()
    app = PDFReplacerApp(root)
    root.mainloop()

