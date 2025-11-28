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
# 0. 配置与初始化
# ------------------------------------------
st.set_page_config(page_title="Python 进阶挑战", layout="centered")
ERROR_LIMIT = 3 

# ------------------------------------------
# 1. 核心状态管理 (存档/读档逻辑)
# ------------------------------------------

def init_session_state():
    """初始化 Session State，确保所有键存在"""
    defaults = {
        'level': 1,
        'score': 0,
        'review_history': [],
        'history_cursor': 0,
        'question_loaded': False,
        'code_initial_value': "",
        'code_input_key': "",
        'code_input_widget_key': "",
        'qa_query_input': "",
        'qa_response': "",
        'solved': False,
        'hint_index': 0,
        'error_count': 0
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # 如果是第一次初始化且没有题目，生成第一题
    if not st.session_state.review_history:
        initial_q = get_question(1)
        st.session_state.review_history.append(create_new_q_state(initial_q))
        load_q_state_from_history()

def load_q_state_from_history():
    """从历史记录同步当前题目状态"""
    if not st.session_state.review_history:
        return
        
    try:
        idx = st.session_state.history_cursor
        # 保护：防止索引越界
        if idx >= len(st.session_state.review_history):
            st.session_state.history_cursor = len(st.session_state.review_history) - 1
            idx = st.session_state.history_cursor

        q_state = st.session_state.review_history[idx]
        st.session_state.current_q = q_state['question']
        st.session_state.solved = q_state['user_state']['solved']
        st.session_state.hint_index = q_state['user_state']['hint_index']
        st.session_state.error_count = q_state['user_state']['error_count']
        
        # 恢复代码内容
        saved_code = q_state['user_state']['user_code']
        st.session_state.code_initial_value = saved_code
        st.session_state.code_input_key = saved_code
        st.session_state.code_input_widget_key = saved_code
    except Exception as e:
        st.error(f"加载题目状态出错: {e}")

def save_current_q_state(current_code=None):
    """保存当前题目的状态到历史列表"""
    if st.session_state.review_history:
        idx = st.session_state.history_cursor
        current_state = st.session_state.review_history[idx]
        current_state['user_state']['solved'] = st.session_state.solved
        current_state['user_state']['hint_index'] = st.session_state.hint_index
        current_state['user_state']['error_count'] = st.session_state.error_count
        
        # 使用传入的代码或 session 中的代码
        code = current_code if current_code is not None else st.session_state.code_input_key
        current_state['user_state']['user_code'] = code
        st.session_state.review_history[idx] = current_state

def get_current_progress_json():
    """将当前进度打包成 JSON 字符串"""
    # 先保存当前状态
    save_current_q_state() 
    data = {
        'level': st.session_state.level,
        'score': st.session_state.score,
        'review_history': st.session_state.review_history,
        'history_cursor': st.session_state.history_cursor
    }
    return json.dumps(data, ensure_ascii=False, indent=4)

def load_progress_from_json(json_data):
    """从 JSON 数据恢复进度"""
    try:
        data = json.load(json_data)
        st.session_state.level = data.get('level', 1)
        st.session_state.score = data.get('score', 0)
        st.session_state.review_history = data.get('review_history', [])
        st.session_state.history_cursor = data.get('history_cursor', 0)
        
        # 加载完成后，立即同步题目显示
        load_q_state_from_history()
        st.success(f"✅ 成功读取存档！当前等级: Lv.{st.session_state.level}")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error(f"❌ 读取存档失败: 文件格式错误。详情: {e}")

# ------------------------------------------
# 2. 题库逻辑 (多样化题库)
# ------------------------------------------

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

# === 动态题目生成器 (Level 6+) ===
def generate_sum_question(level):
    limit = (level - 5) * 4 + 10 
    total = sum(i for i in range(1, limit + 1) if i % 3 == 0)
    solution = f"total = 0\nfor i in range(1, {limit + 1}):\n    if i % 3 == 0:\n        total += i\nprint(total)"
    return {"title": f"Lv.{level} 挑战：条件累加", "desc": f"计算 1 到 {limit} 之间所有能被 3 整除的数之和。", "pre_code": "", "expected": str(total), "hints": ["for循环", "if i % 3 == 0", "total += i"], "final_solution": solution}

def generate_loop_print_question(level):
    size = (level - 5) + 3 
    expected = "\n".join(["*" * size] * size)
    solution = f"size = {size}\nfor i in range(size):\n    print('*' * size)"
    return {"title": f"Lv.{level} 挑战：绘制正方形", "desc": f"打印一个 {size}x{size} 的星号正方形。", "pre_code": "", "expected": expected, "hints": ["嵌套循环", "或者 print('*' * n)"], "final_solution": solution}

def generate_list_math_question(level):
    list_len = 4 + (level // 3) 
    nums = [random.randint(5, 15) for _ in range(list_len)]
    average = int(sum(nums) / len(nums))
    solution = f"nums = {nums}\ntotal = 0\nfor n in nums:\n    total += n\nprint(total // len(nums))"
    return {"title": f"Lv.{level} 挑战：列表平均值", "desc": f"计算列表 `nums = {nums}` 的平均值（取整）。", "pre_code": f"nums = {nums}", "expected": str(average), "hints": ["求和", "除以长度", "取整 //"], "final_solution": solution}

def get_question(level):
    if level in questions_db:
        return random.choice(questions_db[level])
    else:
        generators = [generate_sum_question, generate_loop_print_question, generate_list_math_question]
        return random.choice(generators)(level)

def create_new_q_state(q_data):
    if 'hints' not in q_data: q_data['hints'] = []
    return {'question': q_data, 'user_state': {'solved': False, 'hint_index': 0, 'error_count': 0, 'user_code': ""}}

# ------------------------------------------
# 3. 页面逻辑与交互
# ------------------------------------------

# 初始化应用状态
init_session_state()

# === 侧边栏：存档管理 (解决云端丢失问题) ===
st.sidebar.header("📂 存档管理 (云端必用)")
st.sidebar.info("⚠️ 注意：云端网页关闭后进度会丢失。请在离开前**下载存档**，下次回来**上传存档**即可继续。")

# 1. 导出存档
current_progress_json = get_current_progress_json()
st.sidebar.download_button(
    label="💾 下载当前进度 (保存到本地)",
    data=current_progress_json,
    file_name=f"python_challenge_lv{st.session_state.level}.json",
    mime="application/json"
)

# 2. 导入存档
uploaded_file = st.sidebar.file_uploader("📂 读取本地存档 (恢复进度)", type="json")
if uploaded_file is not None:
    # 增加一个按钮来确认加载，避免重复触发
    if st.sidebar.button("确认读取"):
        load_progress_from_json(uploaded_file)

st.sidebar.divider()
st.sidebar.header("📊 当前状态")
st.sidebar.write(f"**难度:** Level {st.session_state.level}")
st.sidebar.write(f"**得分:** {st.session_state.score}")

# --- 主界面 ---
q = st.session_state.current_q
total_q = len(st.session_state.review_history)

st.title("🐍 Python 进阶挑战")
st.progress(min(st.session_state.level / 100.0, 1.0))

# 导航栏
c1, c2 = st.columns([1, 4])
with c1:
    if st.button("⬅️ 上一题", disabled=(st.session_state.history_cursor == 0)):
        save_current_q_state()
        st.session_state.history_cursor -= 1
        load_q_state_from_history()
        st.rerun()
with c2:
    st.caption(f"当前题目：{st.session_state.history_cursor + 1} / {total_q}")

st.divider()
st.subheader(f"Level {st.session_state.level}: {q['title']}")
st.info(q['desc'])

if q['pre_code']:
    st.code(q['pre_code'], language='python')

# 代码输入区
def on_text_area_change():
    st.session_state.code_input_key = st.session_state.code_input_widget_key

code_input = st.text_area(
    "输入代码:",
    value=st.session_state.code_input_key,
    height=250,
    key="code_input_widget_key",
    on_change=on_text_area_change,
    disabled=st.session_state.solved and (st.session_state.history_cursor == total_q - 1)
)

# Tab 键支持
components.html(
    """<script>
    const ta = document.querySelector('textarea');
    if(ta){
        ta.addEventListener('keydown', function(e){
            if(e.key==='Tab'){
                e.preventDefault();
                var s=this.selectionStart;
                this.value=this.value.substring(0,this.selectionStart)+"    "+this.value.substring(this.selectionEnd);
                this.selectionEnd=s+4;
            }
        });
    }
    </script>""", 
    height=0
)

# 操作区
c_submit, c_hint, c_redo = st.columns([1, 1, 1])

with c_submit:
    if st.button("🚀 提交运行"):
        user_code = st.session_state.code_input_key
        save_current_q_state(user_code)
        
        full_code = q['pre_code'] + "\n" + user_code
        
        try:
            # 1. 语法检查
            ast.parse(full_code)
            
            # 2. 风格检查
            if st.session_state.level == 1 and "price =" in user_code:
                st.warning("⚠️ 警告：不需要重复定义 `price`，直接使用即可。")

            # 3. 运行代码
            f = io.StringIO()
            with redirect_stdout(f):
                exec(full_code)
            output = f.getvalue().strip()
            
            if output == q['expected']:
                st.balloons()
                st.success("✅ **太棒了！结果正确！**")
                st.session_state.solved = True
                st.session_state.error_count = 0
                save_current_q_state(user_code)
            else:
                st.error("❌ 结果不匹配")
                st.warning(f"你的输出: {output}")
                st.info(f"期望输出: {q['expected']}")
                st.session_state.error_count += 1
                save_current_q_state(user_code)
                
        except Exception as e:
            st.error(f"⚠️ 运行出错: {e}")
            st.session_state.error_count += 1
            save_current_q_state(user_code)

with c_hint:
    if st.button("💡 提示"):
        st.session_state.hint_index += 1
        save_current_q_state()
        st.rerun()

with c_redo:
    if st.session_state.solved and st.button("🔄 重做"):
        st.session_state.solved = False
        st.session_state.error_count = 0
        st.session_state.code_initial_value = ""
        st.session_state.code_input_key = ""
        st.session_state.code_input_widget_key = ""
        save_current_q_state()
        st.rerun()

# 提示展示
if st.session_state.hint_index > 0 and not st.session_state.solved:
    hints = q.get('hints', [])
    for i in range(min(st.session_state.hint_index, len(hints))):
        st.warning(f"提示 {i+1}: {hints[i]}")
    if st.session_state.hint_index > len(hints):
        st.error("答案揭晓：")
        st.code(q['final_solution'])

# 下一关按钮
if st.session_state.solved and st.session_state.history_cursor == total_q - 1:
    st.divider()
    if st.button("➡️ 进入下一关 (Level +1)"):
        st.session_state.level += 1
        st.session_state.history_cursor += 1
        new_q = get_question(st.session_state.level)
        st.session_state.review_history.append(create_new_q_state(new_q))
        load_q_state_from_history()
        st.rerun()

st.divider()
with st.expander("❓ 问答助手"):
    q_input = st.text_input("遇到问题？输入关键词（如 for, range, split）", key="qa_query_input")
    if st.button("🔍 搜索答案"):
        query = q_input.lower().strip()
        if not query:
            st.stop()
            
        # 内置简单回答
        knowledge = {
            "for": "`for i in range(n):` 用于循环 n 次。",
            "print": "`print(x)` 用于将 x 输出到屏幕。",
            "range": "`range(5)` 生成 0,1,2,3,4。",
            "list": "列表用 `[]` 表示，如 `[1, 2, 3]`。"
        }
        
        found = False
        for k, v in knowledge.items():
            if k in query:
                st.success(f"🤖 **速查:** {v}")
                found = True
                break
        
        # 外部链接
        safe_q = urllib.parse.quote(query)
        st.markdown(f"👉 [Google 搜索: {query} Python](https://www.google.com/search?q={safe_q}+Python)")
        st.markdown(f"👉 [ChatGPT 提问](https://chatgpt.com/?q={safe_q})")
