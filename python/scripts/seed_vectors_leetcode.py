"""
Self-contained script: embed 10 leetcode problems and mock solutions.
- Embeddings via Ollama (qwen3-embedding:0.6b, 1024-dim)
- Writes vectors to PostgreSQL via psycopg2 raw SQL
- Zero-pads 1024-dim → 1536-dim to match existing column type
"""

import asyncio
import json
import sys
import aiohttp
import psycopg2

# ─── Config ──────────────────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/embed"
OLLAMA_MODEL = "qwen3-embedding:0.6b"
PG_DSN = "postgresql://postgres:jm050711@localhost:5432/acm_agent"
OLLAMA_DIM = 1024
PG_DIM = 1536  # database column is vector(1536)

# ─── Chinese summaries / descriptions for each problem ────────────────────────
# Generated from the title + tags — synthetic because raw_detail lacks description

PROBLEM_META = {
    "11": {
        "summary": "盛水最多的容器：给定数组height，每个元素代表垂直线高度，找两条线使它们与x轴围成的容器能盛最多水。核心思路：双指针从两端向中间移动，每次移动较短的那条边，O(n)时间复杂度。贪心策略——因为面积受限于较短边，移动长边不会增大面积。",
        "content": "题目：Container With Most Water\n难度：中等\n标签：贪心、数组、双指针\n描述：给定一个长度为 n 的整数数组 height，有 n 条垂直线，第 i 条线的两个端点是 (i, 0) 和 (i, height[i])。找出其中的两条线，使得它们与 x 轴共同构成的容器可以容纳最多的水。返回容器可以储存的最大水量。容器不能倾斜。",
    },
    "15": {
        "summary": "三数之和：给定整数数组nums，找出所有和为0且不重复的三元组。核心思路：排序 + 固定一个数 + 双指针找另外两个数。关键去重：外层跳过重复的固定值，内层找到解后跳过重复的左右指针。时间复杂度O(n^2)。",
        "content": "题目：3Sum\n难度：中等\n标签：数组、双指针、排序\n描述：给定一个整数数组 nums，判断是否存在三元组 [nums[i], nums[j], nums[k]] 满足 i != j, i != k, j != k 且 nums[i] + nums[j] + nums[k] == 0。返回所有和为 0 且不重复的三元组。",
    },
    "16": {
        "summary": "最接近的三数之和：给定数组nums和目标值target，找三个数使它们的和与target最接近。核心思路：排序 + 固定一个数 + 双指针，过程中维护最接近的和。与3Sum的区别在于不需要去重，而是追踪最小差值。O(n^2)。",
        "content": "题目：3Sum Closest\n难度：中等\n标签：数组、双指针、排序\n描述：给定一个长度为 n 的整数数组 nums 和一个目标值 target，从 nums 中选出三个整数，使它们的和与 target 最接近。返回这三个数的和。假定每组输入只存在恰好一个解。",
    },
    "18": {
        "summary": "四数之和：给定数组nums和目标值target，找所有和为target且不重复的四元组。核心思路：排序 + 双重循环固定前两个数 + 双指针找后两个数。可以剪枝优化——提前判断最小/最大可能和。时间复杂度O(n^3)。",
        "content": "题目：4Sum\n难度：中等\n标签：数组、双指针、排序\n描述：给定一个包含 n 个整数的数组 nums 和一个目标值 target，找出所有满足 nums[a] + nums[b] + nums[c] + nums[d] == target 的四元组，其中 a、b、c、d 互不相同。返回所有不重复的四元组。",
    },
    "19": {
        "summary": "删除链表倒数第N个节点：给定单链表，删除倒数第n个节点并返回头结点。核心思路：快慢双指针，快指针先走n步，然后同时移动直到快指针到达末尾，此时慢指针指向待删除节点的前驱。使用哑节点dummy简化头结点删除的边界情况。",
        "content": "题目：Remove Nth Node From End of List\n难度：中等\n标签：链表、双指针\n描述：给定一个单链表，删除链表的倒数第 n 个结点，并返回链表的头结点。n 从 1 开始计数。要求一趟扫描完成。",
    },
    "26": {
        "summary": "删除有序数组中的重复项：给定非严格递增排列的数组nums，原地删除重复元素使每个元素只出现一次，返回新长度。核心思路：快慢双指针——慢指针维护已处理的不重复区域，快指针遍历。遇到不同元素时慢指针前移并覆盖。",
        "content": "题目：Remove Duplicates from Sorted Array\n难度：简单\n标签：数组、双指针\n描述：给定一个非严格递增排列的数组 nums，原地删除重复出现的元素，使每个元素只出现一次，并返回移除后数组的新长度。不要使用额外的数组空间，必须在原地修改输入数组。",
    },
    "27": {
        "summary": "移除元素：给定数组nums和值val，原地移除所有等于val的元素，返回新长度。核心思路：快慢双指针，快指针扫描，当元素不等于val时复制到慢指针位置并移动慢指针。相当于把不需要的元素过滤掉。",
        "content": "题目：Remove Element\n难度：简单\n标签：数组、双指针\n描述：给定一个数组 nums 和一个值 val，原地移除所有数值等于 val 的元素，并返回移除后数组的新长度。不要使用额外的数组空间，元素的顺序可以改变。",
    },
    "28": {
        "summary": "找出字符串中第一个匹配项的下标：给定字符串haystack和needle，返回needle在haystack中第一次出现的下标。核心思路：KMP算法构建next数组实现O(n+m)匹配，或使用Rabin-Karp滚动哈希。简单场景可用暴力匹配（切片比较）。",
        "content": "题目：Find the Index of the First Occurrence in a String\n难度：简单\n标签：双指针、字符串、字符串匹配\n描述：给定两个字符串 haystack 和 needle，在 haystack 中找出 needle 的第一个匹配项的下标（从 0 开始）。如果 needle 不是 haystack 的一部分，则返回 -1。",
    },
    "31": {
        "summary": "下一个排列：将给定数字序列重新排列成字典序中下一个更大的排列，若不存在则重排为最小排列。核心思路：从右找第一个降序对(i, i+1)，再从右找第一个大于nums[i]的数与之交换，最后反转i+1到末尾。O(n)时间。",
        "content": "题目：Next Permutation\n难度：中等\n标签：数组、双指针\n描述：整数数组的一个排列就是将其所有成员以序列或线性顺序排列。整数数组的下一个排列是指其整数的下一个字典序更大的排列。如果不存在下一个更大的排列，则必须将数组重新排列成字典序最小的排列。必须原地修改，只允许使用额外常数空间。",
    },
    "5": {
        "summary": "最长回文子串：给定字符串s，找出其中最长的回文子串。核心思路：中心扩展法——遍历每个可能的回文中心（奇数和偶数长度），向两边扩展直到不再是回文，记录最长者。也可用Manacher算法在O(n)内解决，或动态规划O(n^2)。",
        "content": "题目：Longest Palindromic Substring\n难度：中等\n标签：双指针、字符串、动态规划\n描述：给定一个字符串 s，找到 s 中最长的回文子串。如果字符串的长度为 1000 或更小，返回任意一个最长的回文子串即可。回文串是指正着读和反着读一样的字符串。",
    },
}

# ─── Mock solution templates (in Chinese, per problem) ────────────────────────
MOCK_SOLUTIONS = {
    "11": [
        {"author": "算法笔记", "content": "解法：双指针法\n1. 初始化 left=0, right=n-1, max_area=0\n2. while left < right:\n   - 计算当前面积 area = min(height[left], height[right]) * (right - left)\n   - 更新 max_area = max(max_area, area)\n   - 如果 height[left] < height[right]，则 left++；否则 right--\n3. 返回 max_area\n\n正确性证明：由于面积受限于较短边，移动较长边不可能得到更大面积，因此贪心策略正确。时间复杂度 O(n)，空间复杂度 O(1)。"},
        {"author": "LeetCode官方", "content": "双指针贪心解法（Python实现）：\n```python\ndef maxArea(height):\n    left, right = 0, len(height) - 1\n    ans = 0\n    while left < right:\n        area = min(height[left], height[right]) * (right - left)\n        ans = max(ans, area)\n        if height[left] < height[right]:\n            left += 1\n        else:\n            right -= 1\n    return ans\n```\n关键点：每次移动较短边，因为面积上限由短边决定。只需一次遍历。"},
    ],
    "15": [
        {"author": "算法笔记", "content": "解法：排序 + 双指针\n1. 对数组排序\n2. 遍历 i 从 0 到 n-3：\n   - 如果 nums[i] > 0，直接 break（已排序，后面都>0不可能和为0）\n   - 如果 i>0 且 nums[i]==nums[i-1]，跳过（去重）\n   - 双指针 left=i+1, right=n-1\n   - while left<right:\n     - sum = nums[i]+nums[left]+nums[right]\n     - 如果 sum==0：加入结果，left++ right--，并跳过重复值\n     - 如果 sum<0：left++\n     - 如果 sum>0：right--\n3. 返回结果列表\n\n时间复杂度 O(n^2)，空间 O(1)（排序不计入额外空间）。"},
        {"author": "LeetCode官方", "content": "三数之和 Python 实现：\n```python\ndef threeSum(nums):\n    nums.sort()\n    res = []\n    for i in range(len(nums)-2):\n        if nums[i] > 0: break\n        if i > 0 and nums[i] == nums[i-1]: continue\n        l, r = i+1, len(nums)-1\n        while l < r:\n            s = nums[i] + nums[l] + nums[r]\n            if s < 0: l += 1\n            elif s > 0: r -= 1\n            else:\n                res.append([nums[i], nums[l], nums[r]])\n                while l < r and nums[l] == nums[l+1]: l += 1\n                while l < r and nums[r] == nums[r-1]: r -= 1\n                l += 1; r -= 1\n    return res\n```\n核心：固定一数，双指针找另外两数。去重是难点。"},
    ],
    "16": [
        {"author": "算法笔记", "content": "解法：排序 + 双指针（类似三数之和）\n1. 对数组排序\n2. 初始化 closest = 无穷大\n3. 遍历 i 从 0 到 n-3：\n   - left=i+1, right=n-1\n   - while left<right:\n     - sum = nums[i]+nums[left]+nums[right]\n     - 如果 |sum-target| < |closest-target|，更新 closest\n     - 如果 sum < target：left++；否则 right--（如果等于直接返回）\n4. 返回 closest\n\n时间复杂度 O(n^2)，空间 O(1)。"},
    ],
    "18": [
        {"author": "算法笔记", "content": "解法：排序 + 双重循环 + 双指针\n1. 排序数组\n2. 双重循环固定前两个数(nums[i], nums[j])：\n   - 剪枝优化：如果最小可能和 > target，break\n   - 剪枝优化：如果最大可能和 < target，continue\n   - 去重：跳过重复的 i 和 j\n   - 双指针 left=j+1, right=n-1\n   - while left<right:\n     - sum = nums[i]+nums[j]+nums[left]+nums[right]\n     - 等于 target：加入结果，移动指针并去重\n     - 小于 target：left++；大于 target：right--\n3. 返回结果\n\n时间复杂度 O(n^3)，空间 O(1)。"},
    ],
    "19": [
        {"author": "算法笔记", "content": "解法：快慢双指针 + 哑节点\n1. 创建哑节点 dummy，dummy.next = head\n2. 快指针 fast 先走 n+1 步（多走一步让 slow 停在待删节点的前驱）\n3. 然后 slow 和 fast 同时移动，直到 fast 到达 null\n4. 此时 slow 指向待删除节点的前驱，执行 slow.next = slow.next.next\n5. 返回 dummy.next\n\n时间复杂度 O(L)，L 为链表长度。空间 O(1)。\n边界情况：删除头节点时哑节点保证代码统一。"},
        {"author": "LeetCode官方", "content": "删除倒数第N个节点 Python 实现：\n```python\ndef removeNthFromEnd(head, n):\n    dummy = ListNode(0, head)\n    fast = slow = dummy\n    for _ in range(n + 1):\n        fast = fast.next\n    while fast:\n        fast = fast.next\n        slow = slow.next\n    slow.next = slow.next.next\n    return dummy.next\n```\n关键：哑节点避免头节点删除的特殊处理，fast多走一步确保slow停在正确位置。"},
    ],
    "26": [
        {"author": "算法笔记", "content": "解法：快慢双指针\n1. 如果数组为空，返回 0\n2. slow = 0，fast 从 1 遍历到 n-1\n3. 如果 nums[fast] != nums[slow]：\n   - slow++\n   - nums[slow] = nums[fast]\n4. 返回 slow + 1（长度 = 索引 + 1）\n\n核心思想：slow 维护已处理的不重复区域末尾，遇到新元素就扩展。时间复杂度 O(n)，空间 O(1)。原地修改。"},
    ],
    "27": [
        {"author": "算法笔记", "content": "解法：快慢双指针\n1. slow = 0，fast 从 0 遍历到 n-1\n2. 如果 nums[fast] != val：\n   - nums[slow] = nums[fast]\n   - slow++\n3. 返回 slow（即新数组长度）\n\nslow 指向下一个可以放置有效元素的位置。时间复杂度 O(n)，空间 O(1)。"},
    ],
    "28": [
        {"author": "算法笔记", "content": "解法一：KMP 算法\n1. 构建 needle 的 next 数组（最长相等前后缀）\n2. 在 haystack 中匹配，利用 next 数组在失配时快速跳转\n3. 匹配成功返回起始索引，否则返回 -1\n\n解法二：暴力匹配（适合小规模）\n- 遍历 haystack 每个位置，检查是否与 needle 匹配\n\n时间复杂度：KMP O(n+m)，暴力 O(n*m)。"},
        {"author": "LeetCode官方", "content": "字符串匹配 Python 实现（KMP）：\n```python\ndef strStr(haystack, needle):\n    if not needle: return 0\n    n, m = len(haystack), len(needle)\n    # build next array\n    nxt = [0] * m\n    j = 0\n    for i in range(1, m):\n        while j > 0 and needle[i] != needle[j]:\n            j = nxt[j-1]\n        if needle[i] == needle[j]:\n            j += 1\n        nxt[i] = j\n    # match\n    j = 0\n    for i in range(n):\n        while j > 0 and haystack[i] != needle[j]:\n            j = nxt[j-1]\n        if haystack[i] == needle[j]:\n            j += 1\n        if j == m:\n            return i - m + 1\n    return -1\n```\nKMP核心：利用已匹配信息避免回溯。"},
    ],
    "31": [
        {"author": "算法笔记", "content": "解法：字典序算法（两遍扫描）\n1. 从右向左找到第一个 nums[i] < nums[i+1] 的位置 i（找不到说明已是最大排列，直接反转）\n2. 从右向左找到第一个大于 nums[i] 的数 nums[j]\n3. 交换 nums[i] 和 nums[j]\n4. 反转 i+1 到末尾的子数组\n\n时间复杂度 O(n)，空间 O(1)。\n直观理解：想让下一个排列恰好比当前大，需要找一个尽可能靠右的较小数，和它右侧恰好比它大的数交换，然后让后面的序列最小化。"},
        {"author": "LeetCode官方", "content": "下一个排列 Python 实现：\n```python\ndef nextPermutation(nums):\n    n = len(nums)\n    # step 1: find first decreasing element from right\n    i = n - 2\n    while i >= 0 and nums[i] >= nums[i+1]:\n        i -= 1\n    if i >= 0:\n        # step 2: find first element larger than nums[i] from right\n        j = n - 1\n        while nums[j] <= nums[i]:\n            j -= 1\n        nums[i], nums[j] = nums[j], nums[i]\n    # step 3: reverse suffix\n    l, r = i + 1, n - 1\n    while l < r:\n        nums[l], nums[r] = nums[r], nums[l]\n        l += 1; r -= 1\n```\n时间复杂度 O(n)，空间 O(1)。"},
    ],
    "5": [
        {"author": "算法笔记", "content": "解法：中心扩展法\n1. 遍历每个位置 i（回文中心），分奇数长度和偶数长度两种情况：\n   - 奇数：以 i 为中心向两边扩展\n   - 偶数：以 i 和 i+1 为中心向两边扩展\n2. 在扩展过程中更新最长回文子串的起始位置和长度\n3. 返回最长回文子串\n\n时间复杂度 O(n^2)，空间 O(1)。\n\n进阶：Manacher 算法可在 O(n) 内解决，通过插入分隔符统一奇偶长度，维护最右回文边界和中心点来实现线性时间。"},
        {"author": "LeetCode官方", "content": "最长回文子串 Python 实现（中心扩展）：\n```python\ndef longestPalindrome(s):\n    if not s: return ''\n    start, max_len = 0, 1\n    def expand(l, r):\n        nonlocal start, max_len\n        while l >= 0 and r < len(s) and s[l] == s[r]:\n            if r - l + 1 > max_len:\n                start, max_len = l, r - l + 1\n            l -= 1; r += 1\n    for i in range(len(s)):\n        expand(i, i)      # odd length\n        expand(i, i + 1)  # even length\n    return s[start:start + max_len]\n```\n中心扩展法简洁直观，适合面试手写。DP 解法需要 O(n^2) 时间和空间。"},
    ],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def pad_vector(vec: list[float], target_dim: int) -> list[float]:
    """Zero-pad a vector to target_dim."""
    if len(vec) >= target_dim:
        return vec[:target_dim]
    return vec + [0.0] * (target_dim - len(vec))


def _to_pg_vector(vec: list[float]) -> str:
    """Convert a float list to pgvector literal: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{v:.10f}" for v in vec) + "]"


async def embed_texts(session: aiohttp.ClientSession, texts: list[str]) -> list[list[float]]:
    """Call Ollama /api/embed and return vectors."""
    if not texts:
        return []
    payload = {"model": OLLAMA_MODEL, "input": texts}
    for attempt in range(4):
        try:
            async with session.post(OLLAMA_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                body = await resp.text()
                if resp.status != 200:
                    raise RuntimeError(f"Ollama {resp.status}: {body[:300]}")
                data = json.loads(body)
                embeddings = data.get("embeddings")
                if not embeddings or not isinstance(embeddings, list):
                    raise RuntimeError(f"Unexpected response shape: {str(data)[:300]}")
                # Validate dimensions
                for i, emb in enumerate(embeddings):
                    if len(emb) != OLLAMA_DIM:
                        raise RuntimeError(f"Embedding {i} has {len(emb)} dims, expected {OLLAMA_DIM}")
                return embeddings
        except Exception as e:
            if attempt == 3:
                raise
            delay = 2 ** (attempt + 1)
            print(f"  [retry {attempt+1}/3] Embedding failed: {e}, waiting {delay}s...", flush=True)
            await asyncio.sleep(delay)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    errors: list[str] = []
    problems_embedded = 0
    solutions_embedded = 0

    # 1. Fetch problems from PostgreSQL
    print("1. Fetching leetcode problems from PostgreSQL...")
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        SELECT id, source_id, title, tags_normalized, difficulty_normalized, difficulty_raw
        FROM problems
        WHERE source_platform = 'leetcode' AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    print(f"   Found {len(rows)} problems")
    if len(rows) == 0:
        print("   WARNING: No leetcode problems found!")
        return

    # Build problem list
    problems = []
    for r in rows:
        pid, source_id, title, tags, diff_norm, diff_raw = r
        meta = PROBLEM_META.get(source_id)
        if not meta:
            # Fallback: generate simple summary from available data
            tag_str = ", ".join(tags) if tags else ""
            diff_str = diff_raw or str(diff_norm) if diff_norm else ""
            meta = {
                "summary": f"{title}：一道{diff_str}难度算法题，涉及{tag_str}。需要根据题目要求设计算法并编写代码实现。",
                "content": f"题目：{title}\n难度：{diff_str}\n标签：{tag_str}\n来源：LeetCode #{source_id}",
            }
        problems.append({
            "id": pid,
            "source_id": source_id,
            "title": title,
            "tags": tags or [],
            "diff": diff_raw or str(diff_norm) if diff_norm else "未知",
            "summary": meta["summary"],
            "content": meta["content"],
            "solutions": MOCK_SOLUTIONS.get(source_id, []),
        })

    # Prepare embedding payloads (batch all together for efficiency)
    print("\n2. Generating embeddings via Ollama...")
    # Collect all texts to embed
    all_texts: list[str] = []
    text_map: list[tuple] = []  # (problem_index, text_type, text)
    for i, p in enumerate(problems):
        all_texts.append(p["summary"])
        text_map.append((i, "parent", p["summary"]))
        all_texts.append(p["content"])
        text_map.append((i, "content", p["content"]))
        for si, sol in enumerate(p["solutions"]):
            all_texts.append(sol["content"])
            text_map.append((i, f"solution_{si}", sol["content"]))

    print(f"   Total texts to embed: {len(all_texts)}")
    print(f"   - {len(problems)} problems x 2 (parent + content)")
    sol_count_per_problem = [len(p["solutions"]) for p in problems]
    print(f"   - {sum(sol_count_per_problem)} solutions")

    # Call Ollama (may need to batch if too many)
    async with aiohttp.ClientSession() as session:
        # Ollama can handle ~20+ texts in one call; 10*2+15=35 is fine
        embeddings = await embed_texts(session, all_texts)
    print(f"   Got {len(embeddings)} embeddings (native dim={OLLAMA_DIM}, padded to {PG_DIM})")

    # Map embeddings back to problems
    if len(embeddings) != len(text_map):
        errors.append(f"Mismatch: {len(embeddings)} embeddings vs {len(text_map)} texts")
        print(f"   ERROR: {errors[-1]}")
        cur.close()
        conn.close()
        return

    text_idx = 0
    problem_vecs = {}     # pid -> (parent_vec, content_vec)
    solution_vecs = {}    # temp_key -> vec  (we'll use (pid, solution_index) as key)

    for i, p in enumerate(problems):
        # Parent vector (pad to PG_DIM)
        parent_vec = pad_vector(embeddings[text_idx], PG_DIM)
        text_idx += 1
        # Content vector (pad to PG_DIM)
        content_vec = pad_vector(embeddings[text_idx], PG_DIM)
        text_idx += 1
        problem_vecs[p["id"]] = (parent_vec, content_vec)

        for si, sol in enumerate(p["solutions"]):
            sol_vec = pad_vector(embeddings[text_idx], PG_DIM)
            text_idx += 1
            solution_vecs[(p["id"], si)] = sol_vec

    # 3. Write problem vectors to PostgreSQL
    print("\n3. Writing problem vectors to PostgreSQL...")
    for p in problems:
        pid = p["id"]
        parent_vec, content_vec = problem_vecs[pid]
        try:
            cur.execute(
                """
                UPDATE problems
                SET vector_embedding = %s::vector,
                    content_vector   = %s::vector,
                    updated_at       = NOW()
                WHERE id = %s::uuid
                """,
                (_to_pg_vector(parent_vec), _to_pg_vector(content_vec), pid),
            )
            problems_embedded += 1
        except Exception as e:
            err = f"Problem {p['source_id']} ({pid[:8]}): {e}"
            errors.append(err)
            print(f"   ERROR: {err}")

    print(f"   Updated {problems_embedded}/{len(problems)} problems")

    # 4. Insert mock solutions and write their vectors
    print("\n4. Creating mock solutions and writing their vectors...")
    for p in problems:
        pid = p["id"]
        for si, sol in enumerate(p["solutions"]):
            try:
                # Check if solution already exists
                cur.execute(
                    "SELECT id FROM problem_solutions WHERE problem_id = %s::uuid AND solution_index = %s",
                    (pid, si),
                )
                existing = cur.fetchone()
                if existing:
                    sol_id = existing[0]
                    print(f"   [skip] Solution {p['source_id']}#{si} already exists, updating vector")
                    # Update vector only
                    vec = solution_vecs[(pid, si)]
                    cur.execute(
                        "UPDATE problem_solutions SET vector_embedding = %s::vector, updated_at = NOW() WHERE id = %s::uuid",
                        (_to_pg_vector(vec), sol_id),
                    )
                    solutions_embedded += 1
                else:
                    # Insert new
                    cur.execute(
                        """
                        INSERT INTO problem_solutions (id, problem_id, solution_index, content, author, updated_at)
                        VALUES (gen_random_uuid(), %s::uuid, %s, %s, %s, NOW())
                        RETURNING id
                        """,
                        (pid, si, sol["content"], sol["author"]),
                    )
                    sol_id = cur.fetchone()[0]
                    # Write vector
                    vec = solution_vecs[(pid, si)]
                    cur.execute(
                        "UPDATE problem_solutions SET vector_embedding = %s::vector WHERE id = %s::uuid",
                        (_to_pg_vector(vec), sol_id),
                    )
                    solutions_embedded += 1
                    print(f"   [ok] Solution {p['source_id']}#{si}: {sol_id[:8]}...")
            except Exception as e:
                err = f"Solution {p['source_id']}#{si}: {e}"
                errors.append(err)
                print(f"   ERROR: {err}")

    cur.close()
    conn.close()

    # ─── Report ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("REPORT")
    print("=" * 60)
    print(f"  Problems embedded: {problems_embedded}/{len(problems)}")
    print(f"  Solutions embedded: {solutions_embedded}")
    print(f"  Errors: {len(errors)}")
    if errors:
        for e in errors:
            print(f"    - {e}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
