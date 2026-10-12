import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="mea-india", description="印度外交部 Transcripts / Response to Media Queries 爬虫")
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口（默认无头模式）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="抓取两个栏目的完整列表 -> mea_data/lists/")

    p_fetch = sub.add_parser("fetch", help="逐篇抓取详情页（自动跳过已成功的篇目）")
    p_fetch.add_argument("--limit", type=int, help="每个栏目只抓最新的 N 篇（样例交付用）")
    p_fetch.add_argument("--only-failed", action="store_true", help="只补爬日志中失败过的篇目")

    sub.add_parser("parse", help="解析本地原始 HTML -> mea_data/mea_documents.json")
    sub.add_parser("globalsec", help="用 GlobalSecurity.org 核对没有例行记者会的周")
    sub.add_parser("check", help="生成质量检查报告 -> mea_data/check_report.md")

    args = parser.parse_args()
    headless = not args.headed

    if args.cmd == "list":
        from .lists import crawl_lists

        crawl_lists(headless=headless)
    elif args.cmd == "fetch":
        from .details import crawl_details

        crawl_details(limit=args.limit, only_failed=args.only_failed, headless=headless)
    elif args.cmd == "parse":
        from .parse import write_documents

        write_documents()
    elif args.cmd == "globalsec":
        from .globalsec import run_globalsecurity_check

        run_globalsecurity_check(headless=headless)
    elif args.cmd == "check":
        from .check import generate_report

        generate_report()
