"""
퍼널 일별 집계 배치. raw_events → agg_funnel_daily.
실행: python run_funnel_agg.py [YYYY-MM-DD]  (미지정 시 어제·오늘)
"""
import sys
from datetime import date, timedelta

from repo.analytics_repo import run_funnel_daily_aggregation

def main():
    if len(sys.argv) > 1:
        try:
            d = date.fromisoformat(sys.argv[1])
            dates = [d]
        except ValueError:
            print("Usage: python run_funnel_agg.py [YYYY-MM-DD]")
            sys.exit(1)
    else:
        today = date.today()
        dates = [today - timedelta(days=1), today]

    for d in dates:
        print("Funnel aggregation for", d)
        run_funnel_daily_aggregation(d)
    print("Done.")

if __name__ == "__main__":
    main()
