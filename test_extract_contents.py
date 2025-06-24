import pikepdf
import os
import sys
import traceback

def debug_page_contents(pdf_path, page_num=0):
    """详细调试页面内容流的提取过程"""
    print(f"\n===== 调试 {os.path.basename(pdf_path)} 第 {page_num+1} 页 =====")
    
    try:
        # 打开PDF文件
        pdf = pikepdf.open(pdf_path)
        if page_num >= len(pdf.pages):
            print(f"错误: 页码 {page_num+1} 超出范围，PDF只有 {len(pdf.pages)} 页")
            return
            
        page = pdf.pages[page_num]
        print(f"页面对象类型: {type(page)}")
        
        # 方法1: 直接使用API
        print("\n--- 方法1: 使用pikepdf页面API ---")
        try:
            if hasattr(page, 'get_raw_contents'):
                print("发现 get_raw_contents() 方法")
                raw_bytes = page.get_raw_contents()
                print(f"✅ 成功获取内容流: {len(raw_bytes)} 字节")
                print(f"内容流前50字节: {raw_bytes[:50]}")
            else:
                print("❌ 页面对象没有 get_raw_contents() 方法")
        except Exception as e:
            print(f"❌ get_raw_contents() 失败: {str(e)}")
            traceback.print_exc(file=sys.stdout)
        
        # 方法2: 尝试直接访问/Contents键
        print("\n--- 方法2: 访问页面字典的/Contents键 ---")
        try:
            contents = None
            
            # 尝试字符串键 '/Contents'
            try:
                if '/Contents' in page:
                    contents = page['/Contents']
                    print(f"✅ 通过'/Contents'找到内容: 类型={type(contents)}")
                else:
                    print("❌ 页面字典中没有'/Contents'键")
            except Exception as e:
                print(f"❌ 访问'/Contents'失败: {str(e)}")
            
            # 尝试无斜杠键 'Contents'
            if contents is None:
                try:
                    if 'Contents' in page:
                        contents = page['Contents']
                        print(f"✅ 通过'Contents'找到内容: 类型={type(contents)}")
                    else:
                        print("❌ 页面字典中没有'Contents'键")
                except Exception as e:
                    print(f"❌ 访问'Contents'失败: {str(e)}")
            
            # 尝试Name对象键
            if contents is None:
                try:
                    name_key = pikepdf.Name('Contents')
                    if name_key in page:
                        contents = page[name_key]
                        print(f"✅ 通过pikepdf.Name('Contents')找到内容: 类型={type(contents)}")
                    else:
                        print("❌ 页面字典中没有pikepdf.Name('Contents')键")
                except Exception as e:
                    print(f"❌ 访问pikepdf.Name('Contents')失败: {str(e)}")
            
            # 打印页面字典所有键
            try:
                keys = list(page.keys())
                print(f"页面字典键: {[str(k) for k in keys]}")
            except Exception as e:
                print(f"❌ 无法获取页面字典键: {str(e)}")
            
            # 如果找到内容，尝试读取
            if contents is not None:
                try:
                    if isinstance(contents, pikepdf.Array):
                        print(f"内容是数组，包含 {len(contents)} 个项目")
                        for i, item in enumerate(contents):
                            try:
                                content_bytes = item.read_bytes()
                                print(f"  数组项 {i}: 成功读取 {len(content_bytes)} 字节")
                                print(f"  前50字节: {content_bytes[:50]}")
                            except Exception as e:
                                print(f"  ❌ 无法读取数组项 {i}: {str(e)}")
                    else:
                        try:
                            content_bytes = contents.read_bytes()
                            print(f"✅ 成功读取内容流: {len(content_bytes)} 字节")
                            print(f"内容流前50字节: {content_bytes[:50]}")
                        except Exception as e:
                            print(f"❌ 无法读取内容流: {str(e)}")
                            # 尝试解析间接对象
                            try:
                                if hasattr(contents, 'get_object'):
                                    resolved = contents.get_object()
                                    print(f"解析间接对象后的类型: {type(resolved)}")
                                    try:
                                        if hasattr(resolved, 'read_bytes'):
                                            bytes_data = resolved.read_bytes()
                                            print(f"✅ 解析后成功读取: {len(bytes_data)} 字节")
                                    except Exception as e2:
                                        print(f"❌ 解析后仍无法读取: {str(e2)}")
                            except Exception:
                                pass
                except Exception as e:
                    print(f"❌ 处理内容对象时出错: {str(e)}")
        except Exception as e:
            print(f"❌ 访问页面字典失败: {str(e)}")
        
        # 方法3: 尝试查找继承的内容
        print("\n--- 方法3: 检查继承的内容 ---")
        try:
            parent = page.get('/Parent', None)
            if parent:
                print(f"找到父对象: {type(parent)}")
                try:
                    if '/Contents' in parent:
                        inherited = parent['/Contents']
                        print(f"✅ 父对象包含/Contents: {type(inherited)}")
                        try:
                            if isinstance(inherited, pikepdf.Array):
                                print(f"继承的内容是数组，包含 {len(inherited)} 个项目")
                            else:
                                inherited_bytes = inherited.read_bytes()
                                print(f"✅ 成功读取继承的内容流: {len(inherited_bytes)} 字节")
                        except Exception as e:
                            print(f"❌ 无法读取继承的内容流: {str(e)}")
                    else:
                        print("❌ 父对象不包含/Contents键")
                except Exception as e:
                    print(f"❌ 访问父对象失败: {str(e)}")
            else:
                print("❌ 页面没有父对象")
        except Exception as e:
            print(f"❌ 检查继承内容时出错: {str(e)}")
        
        # 方法4: 深入检查对象结构
        print("\n--- 方法4: 深入分析页面对象结构 ---")
        try:
            # 尝试查找流对象的引用
            if hasattr(page, 'obj') and hasattr(page.obj, 'get_object'):
                print("页面有原始对象属性")
                raw_obj = page.obj
                print(f"原始对象类型: {type(raw_obj)}")
                
                # 检查是否有任何键含有"content"（不区分大小写）
                content_related_keys = []
                try:
                    for k in raw_obj.keys():
                        key_str = str(k).lower()
                        if 'content' in key_str:
                            content_related_keys.append(str(k))
                    
                    if content_related_keys:
                        print(f"发现可能相关的键: {content_related_keys}")
                        for k in content_related_keys:
                            try:
                                obj = raw_obj.get(pikepdf.Name(k.lstrip('/')))
                                print(f"键 {k} 的对象类型: {type(obj)}")
                            except Exception:
                                pass
                    else:
                        print("未找到与内容相关的键")
                except Exception as e:
                    print(f"❌ 检查相关键时出错: {str(e)}")
        except Exception as e:
            print(f"❌ 分析页面结构时出错: {str(e)}")
        
    except Exception as e:
        print(f"❌ 打开或处理PDF时出错: {str(e)}")
        traceback.print_exc(file=sys.stdout)
    finally:
        try:
            pdf.close()
        except:
            pass

if __name__ == "__main__":
    # 测试提取的页面
    debug_page_contents("extracted_pages/page_2_fixed.pdf")
    
    # 如果命令行提供了PDF路径，则使用它
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        page_num = int(sys.argv[2]) - 1 if len(sys.argv) > 2 else 0
        debug_page_contents(pdf_path, page_num) 