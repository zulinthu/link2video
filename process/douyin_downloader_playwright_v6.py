import asyncio
import json
import os
import re
import logging
import traceback
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright._impl._errors import TargetClosedError

# 配置日志
logger = logging.getLogger("DouYinPlaywright")

# Path to the cookie file
# 优先从环境变量获取，其次检查 APP_ROOT (应用根目录)，最后使用当前目录
APP_ROOT = os.getenv("APP_ROOT")
if APP_ROOT:
    DEFAULT_COOKIE_PATH = os.path.join(APP_ROOT, "cookies.txt")
else:
    CURRENT_DIR = Path(__file__).parent.parent
    DEFAULT_COOKIE_PATH = str(CURRENT_DIR / "cookies.txt")

COOKIE_FILE_PATH = os.getenv("DOUYIN_COOKIE_PATH", DEFAULT_COOKIE_PATH)


async def load_cookies_from_file(context, cookie_file_path):
    try:
        if not os.path.exists(cookie_file_path):
             logger.warning(f"Cookie file not found: {cookie_file_path}")
             return

        with open(cookie_file_path, 'r', encoding='utf-8') as f:
            cookies = []
            for line in f:
                if line.startswith('#') or line.strip() == '':
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 7: # 宽松匹配
                    domain = parts[0]
                    path = parts[2]
                    secure = parts[3]
                    expires = parts[4]
                    name = parts[5]
                    value = parts[6]
                    
                    cookies.append({
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": path,
                        "expires": int(float(expires)) if expires and expires != '0' else -1,
                        "httpOnly": False,
                        "secure": secure.lower() == 'true',
                        "sameSite": "Lax"
                    })
            if cookies:
                await context.add_cookies(cookies)
                logger.info(f"Successfully loaded {len(cookies)} cookies from {cookie_file_path}")
            else:
                logger.warning(f"No valid cookies found in {cookie_file_path}")
    except Exception as e:
        logger.error(f"Error loading cookies: {e}")


async def get_aweme_detail(share_url):
    """获取视频的aweme_detail数据"""
    aweme_detail = None
    found_event = asyncio.Event()

    async def intercept_aweme_response(response):
        nonlocal aweme_detail
        try:
            # 只检查特定类型的响应以减少开销
            if 'application/json' in response.headers.get('content-type', '').lower():
                # 检查 URL 特征，避免解析所有 JSON
                if 'aweme/v1/web/aweme/detail' in response.url or 'aweme/detail' in response.url:
                    try:
                        json_body = await response.json()
                        if isinstance(json_body, dict) and 'aweme_detail' in json_body:
                            aweme_detail = json_body['aweme_detail']
                            found_event.set()  # 标记数据找到
                    except Exception:
                        pass
        except Exception:
            pass

    async with async_playwright() as p:
        # 使用 headless 模式
        # 注意：如果设置了 PLAYWRIGHT_BROWSERS_PATH 环境变量，playwright 会自动使用
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            java_script_enabled=True,
            viewport={'width': 1920, 'height': 1080}
        )

        if os.path.exists(COOKIE_FILE_PATH):
            await load_cookies_from_file(context, COOKIE_FILE_PATH)

        page = await context.new_page()
        
        # 拦截特定请求以优化速度（可选，视情况而定）
        # await page.route("**/*.{png,jpg,jpeg,gif,css,woff,woff2}", lambda route: route.abort())
        
        page.on("response", intercept_aweme_response)

        async def navigate_and_wait():
            try:
                # 增加超时时间，某些网络环境下可能较慢
                await page.goto(share_url, wait_until="domcontentloaded", timeout=45000)
                # 不需要完全等待 networkidle，只要拿到数据就行
            except PlaywrightTimeoutError:
                logger.warning("页面加载超时，但可能已获取到 aweme_detail")
            except Exception as e:
                logger.error(f"导航失败: {e}")

        navigation_task = asyncio.create_task(navigate_and_wait())

        try:
            # 等待最多15秒，如果提前拿到数据就退出
            await asyncio.wait_for(found_event.wait(), timeout=15)
        except asyncio.TimeoutError:
            logger.warning("等待网络响应超时，尝试从页面脚本解析...")
            
            # 如果仍未找到，尝试从 script 中提取
            if not aweme_detail:
                try:
                    # 针对 Next.js 或 hydration 数据
                    scripts = await page.query_selector_all('script[id="__UNIVERSAL_DATA_FOR_HYDRATION__"], script[id="RENDER_DATA"]')
                    for script in scripts:
                        content = await script.inner_text()
                        try:
                            # 尝试解析 JSON
                            if content:
                                json_data = json.loads(content)
                                # 深度查找 aweme_detail
                                # 这里简化处理，视具体结构而定
                                if 'aweme_detail' in str(content):
                                    # 简单字符串匹配 fallback
                                    pass 
                        except:
                            pass
                            
                    # 暴力查找所有 script
                    if not aweme_detail:
                         scripts = await page.query_selector_all('script')
                         for script in scripts:
                            content = await script.inner_text()
                            if 'aweme_detail' in content:
                                try:
                                    # 提取 JSON 部分
                                    # 这是一个简化版，实际可能需要正则
                                    pass
                                except:
                                    pass
                except Exception as e:
                    logger.error(f"解析页面脚本失败: {e}")

        finally:
            # 取消导航任务
            if not navigation_task.done():
                navigation_task.cancel()
                try:
                    await navigation_task
                except (asyncio.CancelledError, TargetClosedError):
                    pass

            # 关闭资源
            try:
                await context.close()
                await browser.close()
            except Exception:
                pass

        return aweme_detail

