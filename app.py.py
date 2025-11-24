import streamlit as st
import random
import sys
import io
from contextlib import redirect_stdout
import json 
import os    
import ast 
import time 
import streamlit.components.v1 as components 
import urllib.parse 

# ------------------------------------------
# 0. 数据持久化设置
# ------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_FILE = os.path.join(SCRIPT_DIR, "progress.json")
ERROR_LIMIT = 3 

# ------------------------------------------
# 辅助函数：状态管理 (已进行云端部署优化)
# ------------------------------------------

def load_state():
    """从文件中加载历史进度，若失败则安全返回 None。"""
    try:
        if os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if ('review_history' in data and 
                    'history_cursor' in data):
                    return data
    except Exception as e:
        print(f"Warning: Failed to load progress state safely. Error: {e}")
        pass
    return None

def save_state():
    """保存当前所有关键状态到文件，若失败则安全跳过。"""
    data_to_save = {
        'level': st.session_state.level,
        'score': st.session_state.score,
        'review_history': st.session_state.review_history,
        'history_cursor': st.session_state.history_cursor
    }
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4) 
    except Exception as e:
        print(f"Warning: Could not save progress state. Error: {e}")
        pass

def save_current_q_state(current_code_input=None):
    """将当前的临时状态（solved, hints, errors, code）保存到历史记录中。"""
    if st.session_state.review_history:
        current_state = st.session_state.review_history[st.session_state.history_cursor]
        current_state['user_state']['solved'] = st.session_state.solved
        current_state['user_state']['hint_index'] = st.session_state.hint_index
        current_state['user_state']['error_count'] = st.session_state.error_count
        
        # 优先使用传入的 code_input，否则使用 Session State Key 的值
        # 依赖 on_change 机制将最新的代码存入 code_input_key
        code_to_save = current_code_input if current_code_input is not None else st.session_state.code_input_key
        current_state['user_state']['user_code'] = code_to_save
        
        st.session_state.review_history[st.session_state.history_cursor] = current_state


def load_q_state_from_history():
    """从历史记录中加载状态到当前的 session state。"""
    q_state = st.session_state.review_history[st.session_state.history_cursor]
    st.session_state.current_q = q_state['question']
    st.session_state.solved = q_state['user_state']['solved']
    st.session_state.hint_index = q_state['user_state']['hint_index']
    st.session_state.error_count = q_state['user_state']['error_count']
    st.session_state.code_initial_value = q_state['user_state']['user_code']
    st.session_state.code_input_key = q_state['user_state']['user_code']
    # 加载时，将 code_input_key 也赋给新的 widget key 的初始值
    st.session_state.code_input_widget_key = q_state['user_state']['user_code']
    
# ------------------------------------------
# 辅助函数：回调及逻辑
# ------------------------------------------

def update_code_input_state():
    """将文本框的最新值存入 code_input_key，确保状态同步。"""
    # 将组件最新的值赋给用于逻辑和初始化的 key
    st.session_state.code_input_key = st.session_state.code_input_widget_key
    pass

def check_code_style(question_title, user_code):
    """进行简单的代码风格检查。"""
    warnings = []
    if st.session_state.level == 1 and question_title == "计算苹果总价":
        if "price =" in user_code or "count =" in user_code:
            warnings.append("⚠️ **代码重复警告：** 题目已为你定义了 `price` 和 `count`，请直接使用它们进行计算，不需要重复定义。")
    return warnings

def advance_level_and_clear():
    """进入下一关（新题）。"""
    save_current_q_state()
    st.session_state.history_cursor += 1
    if st.session_state.history_cursor >= len(st.session_state.review_history):
        st.session_state.level += 1 
        new_q = get_question(st.session_state.level) 
        new_q_state = create_new_q_state(new_q)
        st.session_state.review_history.append(new_q_state)
    load_q_state_from_history()
    save_state()

def go_previous_q():
    """导航到上一题（复习）。"""
    save_current_q_state()
    st.session_state.history_cursor -= 1
    load_q_state_from_history()
    save_state()

def go_next_q():
    """导航到下一题（复习）。"""
    save_current_q_state()
    st.session_state.history_cursor += 1
    load_q_state_from_history()
    save_state()
    
def mark_solved_after_hint():
    """手动标记为已解决。"""
    st.session_state.solved = True
    save_current_q_state()
    save_state()

def reset_current_q_for_redo():
    """重置当前题目状态（重做功能）。"""
    st.session_state.solved = False
    st.session_state.hint_index = 0
    st.session_state.error_count = 0
    st.session_state.code_initial_value = ""
    st.session_state.code_input_key = "" 
    st.session_state.code_input_widget_key = ""
    save_current_q_state()
    save_state()


# ------------------------------------------
# 问答区核心逻辑
# ------------------------------------------

def process_qa_query():
    """根据用户在问答区的问题，返回预设答案或生成搜索链接。"""
    
    if 'qa_query_input' not in st.session_state:
        st.session_state.qa_query_input = ""
    if 'qa_response' not in st.session_state:
        st.session_state.qa_response = ""
        
    query_text = st.session_state.qa_query_input.strip()

    if query_text:
        # 1. 内置关键词匹配
        keywords = {
            "print": "**关于 `print` 函数：**\n`print()` 是最常用的函数，作用是将内容输出到屏幕。\n用法：`print('Hello Python')`",
            "变量": "**关于 变量：**\n变量是用于存储数据的容器。\n用法：`score = 100`",
            "for": "**关于 `for` 循环：**\n用于遍历序列。\n结构：`for i in range(5):`",
            "range": "**关于 `range()` 函数：**\n生成整数序列。\n用法：`range(5)` 生成 0,1,2,3,4。",
            "循环": "**关于 循环：**\n重复执行代码块，常用 `for` 和 `while`。",
            "if": "**关于 `if` 条件判断：**\n用于根据条件决定是否执行某段代码。\n结构：`if x > 5: print('Yes')`",
            "缩进": "**关于 Python 缩进：**\n使用 **4 个空格**来定义代码块，这是强制性语法！",
            "split": "**关于 `split()` 方法：**\n将字符串按分隔符切分成列表。\n用法：`'a,b'.split(',')`",
            "列表": "**关于 列表 (List)：**\n存储多个数据的有序集合。\n用法：`nums = [1, 2, 3]`"
        }
        
        internal_answer = ""
        for k, v in keywords.items():
            if k in query_text.lower():
                internal_answer = v
                break
        
        # 2. 外部链接生成
        encoded_query = urllib.parse.quote(query_text)
        
        google_url = f"https://www.google.com/search?q={encoded_query}+Python教程"
        bing_url = f"https://cn.bing.com/search?q={encoded_query}+Python用法"
        gpt_url = f"https://chatgpt.com/?q={encoded_query}" 

        # 3. 组合回复
        if internal_answer:
            st.session_state.qa_response = f"""
            #### 🤖 快速指南 (内置知识库)：
            {internal_answer}
            
            ---
            **🌍 需要更多信息？点击下方链接直接搜索：**
            
            👉 [在 Google 中搜索 "{query_text}"]({google_url})
            👉 [在 Bing 中搜索 "{query_text}"]({bing_url})
            """
        else:
            st.session_state.qa_response = f"""
            🤔 **内置库中暂时没有关于 "{query_text}" 的详细记录。**
            
            **🚀 没关系，您可以点击下方链接，一键直达外部答案：**
            
            👉 [🔍 Google 搜索：{query_text}]({google_url})
            👉 [📘 Bing 搜索：{query_text}]({bing_url})
            👉 [🤖 ChatGPT 提问：{query_text}]({gpt_url})
            """
            
        st.rerun()

# ------------------------------------------
# 1. 配置页面和初始化状态
# ------------------------------------------
st.set_page_config(page_title="Python 进阶闯关", layout="centered")

# === 题库定义 (Level 1-3 固定) ===
questions_db = {
    1: [ 
        {"title": "打印问候语", "desc": "请编写代码，打印出字符串 'Hello Python' (注意大小写，不要多空格)。", "pre_code": "", "expected": "Hello Python", "hints": ["使用 print() 函数", "注意引号"], "final_solution": "print('Hello Python')"},
        {"title": "计算苹果总价", "desc": "已知 price=5, count=3。请计算总价并打印出来。", "pre_code": "price = 5\ncount = 3", "expected": "15", "hints": ["使用 * 符号", "print(price * count)"], "final_solution": "total = price * count\nprint(total)"}
    ],
    2: [ 
        {"title": "找偶数", "desc": "列表 `nums = [1, 2, 3, 4]` 已定义。请用 for 循环遍历，只打印出其中的偶数。", "pre_code": "nums = [1, 2, 3, 4]", "expected": "2\n4", "hints": ["for num in nums:", "if num % 2 == 0:"], "final_solution": "for num in nums:\n    if num % 2 == 0:\n        print(num)"}
    ],
    3: [ 
        {"title": "提取邮箱域名", "desc": "变量 `email = 'tom@gmail.com'`。请使用 split 方法提取并打印出 'gmail.com'。", "pre_code": "email = 'tom@gmail.com'", "expected": "gmail.com", "hints": ["email.split('@')", "取列表第2个元素"], "final_solution": "parts = email.split('@')\nprint(parts[1])"}
    ]
}

# === 动态题目生成引擎 (Level 4+) ===

def generate_sum_question(level):
    """题型1: 累加求和 (考察 for, range, +=)"""
    limit = (level - 3) * 5 + 10 
    total = sum(range(1, limit + 1))
    
    solution = f"""
total = 0
for i in range(1, {limit + 1}):
    total += i
print(total)
"""
    
    return {
        "title": f"Lv.{level} 挑战：累加求和",
        "desc": f"请编写代码，使用 `for` 循环计算从 **1 到 {limit}** (包含 {limit}) 的所有整数之和，并打印结果。",
        "pre_code": "",
        "expected": str(total),
        "hints": ["初始化一个变量 total = 0", f"使用 range(1, {limit + 1})", "在循环中执行 total += i"],
        "final_solution": solution.strip()
    }

def generate_loop_print_question(level):
    """题型2: 指定次数打印 (考察基础循环结构)"""
    count = (level - 3) * 3 + 5
    word = random.choice(["Code", "Python", "Future", "Data", "AI"])
    
    expected = "\n".join([word] * count)
    
    solution = f"""
for i in range({count}):
    print("{word}")
"""
    return {
        "title": f"Lv.{level} 挑战：循环打印",
        "desc": f"请编写代码，将单词 **'{word}'** 打印 **{count}** 次。",
        "pre_code": "",
        "expected": expected,
        "hints": [f"使用 range({count})", "注意缩进", "print函数在循环内"],
        "final_solution": solution.strip()
    }

def generate_list_math_question(level):
    """题型3: 列表数学运算 (考察 list 遍历和运算)"""
    list_len = 3 + (level // 5) 
    nums = [random.randint(1, 5) for _ in range(list_len)]
    
    # 任务：计算列表所有元素的乘积
    product = 1
    for n in nums:
        product *= n
        
    solution = f"""
nums = {nums}
product = 1
for n in nums:
    product *= n
print(product)
"""
    return {
        "title": f"Lv.{level} 挑战：列表乘积",
        "desc": f"列表 `nums = {nums}` 已定义。请编写代码计算列表中所有数字的**乘积**并打印出来。",
        "pre_code": f"nums = {nums}",
        "expected": str(product),
        "hints": ["定义 product = 1", "for n in nums:", "product *= n"],
        "final_solution": solution.strip()
    }

def get_question(level):
    """根据难度等级获取题目。"""
    if level <= 3:
        return random.choice(questions_db[level])
    else:
        generators = [
            generate_sum_question,
            generate_loop_print_question,
            generate_list_math_question
        ]
        selected_gen = random.choice(generators)
        return selected_gen(level)

def create_new_q_state(q_data):
    if 'hints' not in q_data:
        q_data['hints'] = []
    
    return {
        'question': q_data,
        'user_state': {
            'solved': False,
            'hint_index': 0,
            'error_count': 0,
            'user_code': ""
        }
    }

# === 初始化逻辑 ===
loaded_state = load_state()

if 'level' not in st.session_state:
    if loaded_state:
        st.session_state.level = loaded_state.get('level', 1)
        st.session_state.score = loaded_state.get('score', 0)
        st.session_state.review_history = loaded_state.get('review_history', [])
        st.session_state.history_cursor = loaded_state.get('history_cursor', 0)
        st.session_state.question_loaded = True 
    else:
        st.session_state.level = 1 
        st.session_state.score = 0
        st.session_state.question_loaded = False
        st.session_state.review_history = []
        st.session_state.history_cursor = 0
        initial_q = get_question(1)
        st.session_state.review_history.append(create_new_q_state(initial_q))

    st.session_state.code_initial_value = "" 
    st.session_state.code_input_key = "" 
    st.session_state.code_input_widget_key = "" # 初始化新的 widget key
    st.session_state.qa_query_input = "" 
    st.session_state.qa_response = ""

    load_q_state_from_history()
    save_state()

# 确保问答状态存在 (防御性检查)
if 'qa_query_input' not in st.session_state:
    st.session_state.qa_query_input = ""
if 'qa_response' not in st.session_state:
    st.session_state.qa_response = ""
# 确保新的 widget key 存在
if 'code_input_widget_key' not in st.session_state:
    st.session_state.code_input_widget_key = ""


# ------------------------------------------
# 2. 界面显示
# ------------------------------------------
q = st.session_state.current_q
total_q_count = len(st.session_state.review_history)

st.markdown(f"# Python 进阶挑战")
st.markdown(f"### 难度等级：Lv.{st.session_state.level}")

progress_percent = min(st.session_state.level / 100.0, 1.0) 
st.progress(progress_percent) 

st.markdown("---")

col_nav_1, col_nav_2, col_nav_3 = st.columns([1, 2, 1])
with col_nav_2:
    st.caption(f"当前题目：{st.session_state.history_cursor + 1} / {total_q_count}")

st.markdown("---")

st.subheader(f"{q['title']}")
st.info(q['desc'])

if q['pre_code']:
    st.code(q['pre_code'], language='python')
    st.caption("👆 预定义代码 (直接使用变量，无需再次定义)")


is_latest_q = st.session_state.history_cursor == len(st.session_state.review_history) - 1
should_disable_submit = st.session_state.solved and is_latest_q

st.markdown("##### ✍️ 在这里输入你的代码：(**已启用 Tab 缩进**)")

# 使用基础输入框 + JS 增强，通过 on_change 确保代码值同步
code_input = st.text_area(
    label="输入代码:",
    value=st.session_state.code_input_widget_key, # 使用 widget key 的值
    height=200,
    key="code_input_widget_key", # 绑定新的 key
    on_change=update_code_input_state, # 确保输入立即同步到 code_input_key
    disabled=should_disable_submit,
    label_visibility="collapsed"
)

# JS 注入：实现 Tab 键缩进
if not should_disable_submit:
    js_code = """
    <script>
    const textarea = document.querySelector('textarea[aria-label="输入代码:"]');
    if (textarea) {
        textarea.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                e.preventDefault();
                const start = this.selectionStart;
                const end = this.selectionEnd;
                const fourSpaces = '    ';
                this.value = this.value.substring(0, start) + fourSpaces + this.value.substring(end);
                this.selectionStart = this.selectionEnd = start + fourSpaces.length;
            }
        });
    }
    </script>
    """
    components.html(js_code, height=0)


st.markdown("---")

# ------------------------------------------
# 3. 操作按钮
# ------------------------------------------

col_op_1, col_op_2, col_op_3, col_op_4 = st.columns([1, 1, 1, 3])

# === 提交 ===
with col_op_1:
    if st.button("🚀 提交运行", disabled=should_disable_submit): 
        
        # 从 Session State 安全读取最新代码
        user_input_code = st.session_state.code_input_key
        
        save_current_q_state(current_code_input=user_input_code) 
        
        full_code = q['pre_code'] + "\n" + user_input_code 
        
        try:
            ast.parse(full_code) 
        except SyntaxError as e:
            st.error(f"❌ **语法错误：** 请检查缩进和标点。错误：{e}")
            st.session_state.error_count += 1
            save_current_q_state(current_code_input=user_input_code)
            save_state()
            if st.session_state.error_count >= ERROR_LIMIT:
                st.error(f"❌ **连续错误 {ERROR_LIMIT} 次！** 正确答案已显示。")
                st.code(q['final_solution'], language='python')
                st.session_state.solved = True
                save_current_q_state(current_code_input=user_input_code)
                save_state()
                st.stop() 
            st.stop()
            
        style_warnings = check_code_style(q['title'], user_code=user_input_code) 
        if style_warnings:
            for warning in style_warnings:
                st.warning(warning)
            st.write("---") 
        
        f = io.StringIO()
        try:
            with redirect_stdout(f):
                exec(full_code) 
            
            user_output = f.getvalue().strip()
            
            if user_output == q['expected']:
                st.session_state.solved = True 
                st.session_state.error_count = 0 
                save_current_q_state(current_code_input=user_input_code)
                save_state() 
                st.rerun() 
            else:
                st.error("❌ **结果错误：** 输出与期望不符。")
                st.warning(f"你的输出:\n{user_output}")
                st.info(f"期望的正确输出:\n{q['expected']}")
                st.session_state.error_count += 1
                save_current_q_state(current_code_input=user_input_code)
                save_state()
                if st.session_state.error_count >= ERROR_LIMIT:
                    st.error(f"❌ **连续错误 {ERROR_LIMIT} 次！** 正确答案已显示。")
                    st.code(q['final_solution'], language='python')
                    st.session_state.solved = True
                    save_current_q_state(current_code_input=user_input_code)
                    save_state()
                    st.stop()
                
        except Exception as e:
            st.error(f"⚠️ **运行错误：** 代码执行出错。详情：{e}")
            st.session_state.error_count += 1
            save_current_q_state(current_code_input=user_input_code)
            save_state()
            if st.session_state.error_count >= ERROR_LIMIT:
                st.error(f"❌ **连续错误 {ERROR_LIMIT} 次！** 正确答案已显示。")
                st.code(q['final_solution'], language='python')
                st.session_state.solved = True
                save_current_q_state(current_code_input=user_input_code)
                save_state()
                st.stop()

# === 提示 ===
with col_op_2:
    if st.button("💡 提示", disabled=should_disable_submit):
        st.session_state.hint_index += 1
        save_current_q_state()
        save_state()
        st.rerun()

# === 重做 ===
with col_op_3:
    if st.session_state.solved:
        if st.button("🔄 重做", on_click=reset_current_q_for_redo):
            pass

st.markdown("---")

# 提示显示区
if st.session_state.hint_index > 0 and not st.session_state.solved:
    hints_list = q.get('hints', [])
    max_hints = len(hints_list)

    for i in range(min(st.session_state.hint_index, max_hints)):
        st.warning(f"💡 提示 {i+1}: {hints_list[i]}")

    if st.session_state.hint_index > max_hints:
        st.error("🤯 答案揭晓！")
        st.code(q['final_solution'], language='python')
        
        if st.button("✅ 我已理解，进入下一题", on_click=mark_solved_after_hint):
            pass 

# ------------------------------------------
# 4. 导航按钮
# ------------------------------------------

col_nav_L, col_nav_R = st.columns([1, 1])

with col_nav_L:
    is_first_q = st.session_state.history_cursor == 0
    if st.button("⬅️ 上一题", disabled=is_first_q, on_click=go_previous_q):
        pass

with col_nav_R:
    is_latest_q_cursor = st.session_state.history_cursor == total_q_count - 1
    
    with st.container():
        if is_latest_q_cursor and st.session_state.solved:
            if st.button("➡️ 进入下一关", on_click=advance_level_and_clear):
                pass
        elif not is_latest_q_cursor:
            if st.button("➡️ 下一题", on_click=go_next_q):
                pass
        
# ------------------------------------------
# 5. 侧边栏与问答区
# ------------------------------------------

st.sidebar.header("📊 进度")
st.sidebar.write(f"**得分:** {st.session_state.score}")
st.sidebar.write(f"**难度:** Level {st.session_state.level}")
st.sidebar.write(f"**当前错误:** {st.session_state.error_count}/{ERROR_LIMIT}")

st.markdown("---")
with st.expander("❓ 问答区：提出你的疑问"):
    st.text_area(
        "输入你的问题 (例如：什么是 Python 的 for 循环?)", 
        value=st.session_state.qa_query_input, 
        key="qa_query_input", 
        height=80
    )
    
    if st.button("🤔 寻求解答"):
        process_qa_query()

    if st.session_state.qa_response:
        st.markdown("#### **🤖 AI 解答**")
        st.markdown(st.session_state.qa_response)
