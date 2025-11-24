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
# 辅助函数：状态管理 
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
        # 在加载失败时，打印警告，但不崩溃应用
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
        
        # 确保保存的是最新的代码
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
    
    # 确保加载历史代码到所有相关 state key
    history_code = q_state['user_state']['user_code']
    st.session_state.code_initial_value = history_code
    st.session_state.code_input_key = history_code
    st.session_state.code_input_widget_key = history_code
    
# ------------------------------------------
# 辅助函数：回调及逻辑
# ------------------------------------------

def update_code_input_state():
    """将文本框的最新值存入 code_input_key，确保状态同步。"""
    # 此函数在 text_area 更改时调用，是确保持久化代码最新的关键
    st.session_state.code_input_key = st.session_state.code_input_widget_key
    # 每次更新代码时，也保存到历史记录中，增加实时性
    save_current_q_state(current_code_input=st.session_state.code_input_key)
    save_state()
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
# 问答区核心逻辑 (保持不变)
# ------------------------------------------

def process_qa_query():
    """根据用户在问答区的问题，返回预设答案或生成搜索链接。"""
    
    if 'qa_query_input' not in st.session_state:
        st.session_state.qa_query_input = ""
    if 'qa_response' not in st.session_state:
        st.session_state.qa_response = ""
        
    query_text = st.session_state.qa_query_input.strip()

    if query_text:
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
        
        encoded_query = urllib.parse.quote(query_text)
        
        google_url = f"https://www.google.com/search?q={encoded_query}+Python教程"
        bing_url = f"https://cn.bing.com/search?q={encoded_query}+Python用法"
        gpt_url = f"https://chatgpt.com/?q={encoded_query}" 

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

# === 题库定义 (Level 1-5 固定) ===
questions_db = {
    1: [ 
        {"title": "打印问候语", "desc": "请编写代码，打印出字符串 'Hello Python' (注意大小写，不要多空格)。", "pre_code": "", "expected": "Hello Python", "hints": ["使用 print() 函数", "注意引号"], "final_solution": "print('Hello Python')"},
        {"title": "计算苹果总价", "desc": "已知 price=5, count=3。请计算总价并打印出来。", "pre_code": "price = 5\ncount = 3", "expected": "15", "hints": ["使用 * 符号", "print(price * count)"], "final_solution": "total = price * count\nprint(total)"}
    ],
    2: [ 
        {"title": "找偶数", "desc": "列表 `nums = [1, 2, 3, 4]` 已定义。请用 for 循环遍历，只打印出其中的偶数。", "pre_code": "nums = [1, 2, 3, 4]", "expected": "2\n4", "hints": ["for num in nums:", "if num % 2 == 0:"], "final_solution": "for num in nums:\n    if num % 2 == 0:\n        print(num)"},
        {"title": "提取邮箱域名", "desc": "变量 `email = 'tom@gmail.com'`。请使用 split 方法提取并打印出 'gmail.com'。", "pre_code": "email = 'tom@gmail.com'", "expected": "gmail.com", "hints": ["email.split('@')", "取列表第2个元素"], "final_solution": "parts = email.split('@')\nprint(parts[1])"}
    ],
    3: [
        {"title": "统计元音字母", "desc": "计算并打印字符串 `s = 'Python'` 中元音字母（a, e, i, o, u）的总个数。", "pre_code": "s = 'Python'\nvowels = 'aeiou'", "expected": "1", "hints": ["初始化 count = 0", "用 for 循环遍历字符串", "用 if letter in vowels: 判断"], "final_solution": "count = 0\nfor char in s.lower():\n    if char in vowels:\n        count += 1\nprint(count)"}
    ],
    4: [
        {"title": "字典库存更新", "desc": "字典 `inventory = {'apple': 10, 'banana': 5}` 已定义。请将 'banana' 的库存数量增加 3，并打印更新后的 'banana' 库存数量。", "pre_code": "inventory = {'apple': 10, 'banana': 5}", "expected": "8", "hints": ["使用方括号 `[]` 访问键值", "使用 `+=` 进行累加操作"], "final_solution": "inventory['banana'] += 3\nprint(inventory['banana'])"}
    ],
    5: [
        {"title": "定义乘方函数", "desc": "请定义一个名为 `power_of_two` 的函数，它接受一个参数 `n`，并返回 `n` 的 2 次方。然后调用此函数，传入 7 并打印结果。", "pre_code": "", "expected": "49", "hints": ["使用 `def` 关键字定义函数", "函数体内使用 `return n ** 2`"], "final_solution": "def power_of_two(n):\n    return n ** 2\n\nprint(power_of_two(7))"}
    ]
}

# === 动态题目生成引擎 (Level 6+) ===

def generate_sum_question(level):
    """Gen 1: 复杂累加求和 (考察 for, range, if 过滤, +=) - 行数递增"""
    # 难度与行数正相关：增加条件判断
    limit = (level - 5) * 4 + 10 
    
    # 任务：计算 1 到 limit 中所有能被 3 整除的数字之和
    total = sum(i for i in range(1, limit + 1) if i % 3 == 0)
    
    solution = f"""
# 难度递增: 筛选并求和
total = 0
for i in range(1, {limit + 1}):
    if i % 3 == 0:
        total += i
print(total)
""" # 5-6 行代码
    return {
        "title": f"Lv.{level} 挑战：复杂条件累加",
        "desc": f"请编写代码，计算从 **1 到 {limit}** 中，所有能被 **3 整除**的整数之和，并打印结果。",
        "pre_code": "",
        "expected": str(total),
        "hints": ["使用 `for` 循环和 `range`", "在循环内使用 `if i % 3 == 0` 进行判断"],
        "final_solution": solution.strip()
    }

def generate_loop_print_question(level):
    """Gen 2: 嵌套循环打印 (考察嵌套循环) - 行数递增"""
    # 难度与行数正相关：增加嵌套和条件
    size = (level - 5) + 3 
    
    # 任务：打印一个 size*size 的星号正方形
    expected = "\n".join(["*" * size] * size)
    
    solution = f"""
size = {size}
for i in range(size):
    # 嵌套循环或打印
    print("*" * size)
""" # 3-4 行代码
    return {
        "title": f"Lv.{level} 挑战：绘制正方形",
        "desc": f"请使用循环，打印一个 **{size}x{size}** 的星号（`*`）正方形。",
        "pre_code": "",
        "expected": expected,
        "hints": [f"使用 range({size})", "在循环内使用 `print('*' * size)`"],
        "final_solution": solution.strip()
    }

def generate_list_math_question(level):
    """Gen 3: 列表平均值计算 (考察 list 遍历, 求和, 长度, 浮点数) - 行数递增"""
    list_len = 4 + (level // 3) 
    nums = [random.randint(5, 15) for _ in range(list_len)]
    
    # 任务：计算列表所有元素的平均值 (向下取整)
    average = int(sum(nums) / len(nums))
        
    solution = f"""
nums = {nums}
total = 0
for n in nums:
    total += n
# 计算平均值并向下取整
avg = total // len(nums)
print(avg)
""" # 5-6 行代码
    return {
        "title": f"Lv.{level} 挑战：列表平均值",
        "desc": f"列表 `nums = {nums}` 已定义。请编写代码计算列表中所有数字的**平均值**（取整数部分），并打印出来。",
        "pre_code": f"nums = {nums}",
        "expected": str(average),
        "hints": ["先求和，再除以 `len(nums)`", "使用整数除法 `//`"],
        "final_solution": solution.strip()
    }

def generate_string_reverse_question(level):
    """Gen 4: 字符串切片与拼接 (考察切片/列表操作) - 行数递增"""
    original_word = random.choice(["algorithm", "challenge", "programming", "openai", "python"])
    
    # 任务：先反转字符串，然后将其转换为大写
    reversed_upper = original_word[::-1].upper()
    
    solution = f"""
word = '{original_word}'
# 反转
reversed_word = word[::-1]
# 转大写
final_result = reversed_word.upper()
print(final_result)
""" # 4-5 行代码
    return {
        "title": f"Lv.{level} 挑战：反转并大写",
        "desc": f"变量 `word = '{original_word}'`。请编写代码将这个字符串**反转**后，再将所有字母转换为**大写**，并打印结果。",
        "pre_code": f"word = '{original_word}'",
        "expected": reversed_upper,
        "hints": ["使用 `[::-1]` 进行反转", "使用 `.upper()` 方法"],
        "final_solution": solution.strip()
    }

def generate_conditional_list_filter_question(level):
    """Gen 5: 列表推导式或双重条件过滤 (考察双重 if) - 行数递增"""
    # 难度与行数正相关：增加两个条件
    lower_limit = (level - 5) + 3 
    upper_limit = lower_limit + 5
    nums = [random.randint(1, 15) for _ in range(7 + (level // 4))]
    
    # 任务：筛选出在 (lower_limit, upper_limit) 之间且为偶数的数字个数
    filtered_count = len([n for n in nums if n > lower_limit and n < upper_limit and n % 2 == 0])
    
    solution = f"""
nums = {nums}
lower = {lower_limit}
upper = {upper_limit}
count = 0
for n in nums:
    if n > lower and n < upper:
        if n % 2 == 0:
            count += 1
print(count)
""" # 7-8 行代码
    return {
        "title": f"Lv.{level} 挑战：复杂双重筛选",
        "desc": f"列表 `nums = {nums}`。请编写代码筛选出**大于 {lower_limit} 且小于 {upper_limit}，同时为偶数**的数字的个数，并打印结果。",
        "pre_code": f"nums = {nums}\nlower = {lower_limit}\nupper = {upper_limit}",
        "expected": str(filtered_count),
        "hints": ["需要两个 `if` 条件或一个 `if` + `and`", "最后打印计数器的值"],
        "final_solution": solution.strip()
    }


def get_question(level):
    """根据难度等级获取题目。"""
    if level in questions_db:
        return random.choice(questions_db[level])
    else:
        # Level 6+ 动态抽取，确保多样性
        generators = [
            generate_sum_question,
            generate_loop_print_question,
            generate_list_math_question,
            generate_string_reverse_question,
            generate_conditional_list_filter_question
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
            'user_code': "" # 初始代码为空
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
    st.session_state.code_input_widget_key = "" 
    st.session_state.qa_query_input = "" 
    st.session_state.qa_response = ""

    load_q_state_from_history()
    save_state()

# 确保问答状态存在 (防御性检查)
if 'qa_query_input' not in st.session_state:
    st.session_state.qa_query_input = ""
if 'qa_response' not in st.session_state:
    st.session_state.qa_response = ""
if 'code_input_widget_key' not in st.session_state:
    # 确保重启后 text_area 的 key 至少有空字符串
    st.session_state.code_input_widget_key = st.session_state.code_input_key


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

# 使用基础输入框，通过 on_change 确保代码值同步和持久化
code_input = st.text_area(
    label="输入代码:",
    value=st.session_state.code_input_key, # 使用 code_input_key 作为值来源
    height=200,
    key="code_input_widget_key", # widget key
    on_change=update_code_input_state, # 每次更改都调用保存
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
        
        # 确保提交时获取最新的代码
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
            if st.session_state.error_count < ERROR_LIMIT:
                 st.warning(f"💡 **提示：** 还可以尝试 {ERROR_LIMIT - st.session_state.error_count} 次。")
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
                st.balloons() 
                st.success("✅ **恭喜你！代码运行结果正确！**") 
                
                st.session_state.solved = True 
                st.session_state.error_count = 0 
                save_current_q_state(current_code_input=user_input_code)
                save_state() 
                
            else:
                st.error("❌ **结果错误：** 输出与期望不符。")
                st.warning(f"你的输出:\n{user_output}")
                st.info(f"期望的正确输出:\n{q['expected']}")
                st.session_state.error_count += 1
                
                if st.session_state.error_count < ERROR_LIMIT:
                    st.warning(f"💡 **提示：** 还可以尝试 {ERROR_LIMIT - st.session_state.error_count} 次。") 
                
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
            
            if st.session_state.error_count < ERROR_LIMIT:
                st.warning(f"💡 **提示：** 还可以尝试 {ERROR_LIMIT - st.session_state.error_count} 次。") 
            
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
