import logging
import time
import os
import json
import asyncio
from process.douyin_downloader_playwright_v6 import get_aweme_detail
from process.download import Download
from .result import Result

# 配置logger
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
# 改名为douyin_logger以避免冲突
douyin_logger = logging.getLogger("DouYin")


def handle_aweme_download(share_url, base_path="downloads"):
    """处理单个作品下载"""
    # 实例化 Result 和 Download 对象，避免全局变量导致的线程安全问题
    result_handler = Result()
    downloader = Download(
        thread=1,
        music=True,
        cover=True,
        avatar=True,
        resjson=True,
        folderstyle=False  # 禁用文件夹模式，直接下载到指定目录
    )

    douyin_logger.info("[  提示  ]:正在请求单个作品")

    # 最大重试次数
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            douyin_logger.info(f"[  提示  ]:第 {retry_count + 1} 次尝试获取作品信息")
            # 获取url数据
            aweme_data = asyncio.run(get_aweme_detail(share_url))
            raw = json.dumps(aweme_data, indent=2, ensure_ascii=False)
            datadict = json.loads(raw)

            # 使用局部实例处理数据
            result_handler.dataConvert(0, result_handler.awemeDict, datadict)
            result = result_handler.awemeDict

            if not result:
                douyin_logger.error("[  错误  ]:获取作品信息失败")
                retry_count += 1
                if retry_count < max_retries:
                    douyin_logger.info("[  提示  ]:等待 5 秒后重试...")
                    time.sleep(5)
                continue

            # 直接使用返回的字典，不需要解包
            datanew = result

            if datanew:
                # 使用传入的 base_path
                awemePath = base_path
                os.makedirs(awemePath, exist_ok=True)

                # 下载前检查视频URL
                video_url = datanew.get("video", {}).get("play_addr", {}).get("url_list", [])
                if not video_url or len(video_url) == 0:
                    douyin_logger.error("[  错误  ]:无法获取视频URL")
                    retry_count += 1
                    if retry_count < max_retries:
                        douyin_logger.info("[  提示  ]:等待 5 秒后重试...")
                        time.sleep(5)
                    continue

                douyin_logger.info(f"[  提示  ]:获取到视频URL，准备下载")
                # 使用局部实例下载
                downloader.userDownload(awemeList=[datanew], savePath=awemePath)
                douyin_logger.info(f"[  成功  ]:视频下载完成")
                return awemePath
            else:
                douyin_logger.error("[  错误  ]:作品数据为空")
                retry_count += 1
            if retry_count < max_retries:
                douyin_logger.info("[  提示  ]:等待 5 秒后重试...")
                time.sleep(5)

        except Exception as e:
            douyin_logger.error(f"[  错误  ]:处理作品时出错: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                douyin_logger.info("[  提示  ]:等待 5 秒后重试...")
                time.sleep(5)

    douyin_logger.error("[  失败  ]:已达到最大重试次数，无法下载视频")
