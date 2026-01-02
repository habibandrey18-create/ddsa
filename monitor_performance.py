#!/usr/bin/env python3
"""
Performance monitoring and optimization script
Monitors bot performance and provides optimization recommendations
"""

import sys
import os
import asyncio
import time
from datetime import datetime, timedelta
import statistics

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def monitor_system_performance():
    """Monitor current system performance"""
    print("=== SYSTEM PERFORMANCE MONITOR ===")

    try:
        from services.monitoring_service import get_monitoring_service
        from redis_cache import get_redis_cache
        from services.affiliate_tracking_service import get_affiliate_tracking_service

        monitoring = get_monitoring_service()
        affiliate_service = get_affiliate_tracking_service()

        # Get current metrics
        metrics = monitoring.get_current_metrics()
        alerts = monitoring.check_alerts()

        print(f"Current Metrics (5 min avg):")
        print(f"  Parsing Success Rate: {metrics.get('parsing_success_rate', 0):.1f}%")
        print(f"  CAPTCHA Rate: {metrics.get('captcha_rate', 0):.1f}/min")
        print(f"  HTTP 429 Rate: {metrics.get('http_429_rate', 0):.1f}/min")
        print(f"  Proxy Success Rate: {metrics.get('avg_proxy_success_rate', 0):.1f}%")
        print(f"  Active Proxies: {metrics.get('active_proxies', 0)}")
        print(f"  Queue Size: {metrics.get('queue_size', 0)}")
        print(f"  Publish Rate: {metrics.get('publish_rate', 0):.1f}/min")

        print(f"\nActive Alerts: {len(alerts)}")
        for alert in alerts:
            print(f"  {alert['severity'].upper()}: {alert['name']}")

        # Get affiliate stats
        affiliate_stats = affiliate_service.get_overall_stats(days=1)
        print("\nAffiliate Performance (24h):")
        print(f"  Total Links: {affiliate_stats.get('total_links', 0)}")
        print(f"  Total Clicks: {affiliate_stats.get('total_clicks', 0)}")
        print(f"  Overall CTR: {affiliate_stats.get('overall_ctr', 0):.2f}%")

        # Get Redis stats
        try:
            # For local monitoring, try to connect directly to localhost Redis
            import redis as redis_lib
            local_redis = redis_lib.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            local_redis.ping()  # Test connection

            # Use local Redis for stats
            redis_stats = {
                'connected_clients': local_redis.info().get('connected_clients', 0),
                'used_memory_human': local_redis.info().get('used_memory_human', '0B'),
                'publish_buffer_size': local_redis.zcard('publish_buffer'),
                'brand_window_size': local_redis.llen('recent:brands'),
            }
            print("\nRedis Stats:")
            print(f"  Connected Clients: {redis_stats.get('connected_clients', 0)}")
            print(f"  Used Memory: {redis_stats.get('used_memory_human', '0B')}")
            print(f"  Publish Buffer Size: {redis_stats.get('publish_buffer_size', 0)}")
            print(f"  Brand Window Size: {redis_stats.get('brand_window_size', 0)}")
        except:
            print("\nRedis Stats: Not available")

        return metrics, alerts, affiliate_stats

    except Exception as e:
        print(f"Error monitoring performance: {e}")
        return None, [], {}

def analyze_performance_data(metrics, alerts, affiliate_stats):
    """Analyze performance data and provide recommendations"""
    print("\n=== PERFORMANCE ANALYSIS & RECOMMENDATIONS ===")

    recommendations = []

    # Analyze parsing success rate
    parsing_rate = metrics.get('parsing_success_rate', 100)
    if parsing_rate < 50:
        recommendations.append({
            'priority': 'CRITICAL',
            'issue': f'Low parsing success rate ({parsing_rate:.1f}%)',
            'recommendation': 'Check proxy quality, increase delays, monitor for shadow-ban'
        })
    elif parsing_rate < 80:
        recommendations.append({
            'priority': 'HIGH',
            'issue': f'Moderate parsing success rate ({parsing_rate:.1f}%)',
            'recommendation': 'Monitor proxy performance, consider adding more proxies'
        })

    # Analyze CAPTCHA rate
    captcha_rate = metrics.get('captcha_rate', 0)
    if captcha_rate > 10:
        recommendations.append({
            'priority': 'HIGH',
            'issue': f'High CAPTCHA rate ({captcha_rate:.1f}/min)',
            'recommendation': 'Increase request delays, rotate proxies more frequently'
        })

    # Analyze HTTP 429 rate
    http_429_rate = metrics.get('http_429_rate', 0)
    if http_429_rate > 5:
        recommendations.append({
            'priority': 'MEDIUM',
            'issue': f'High HTTP 429 rate ({http_429_rate:.1f}/min)',
            'recommendation': 'Increase delays between requests, reduce concurrent requests'
        })

    # Analyze proxy quality
    proxy_success_rate = metrics.get('avg_proxy_success_rate', 100)
    active_proxies = metrics.get('active_proxies', 0)
    if proxy_success_rate < 50:
        recommendations.append({
            'priority': 'HIGH',
            'issue': f'Low proxy quality ({proxy_success_rate:.1f}%)',
            'recommendation': 'Test and replace failing proxies, add more proxy sources'
        })
    if active_proxies == 0:
        recommendations.append({
            'priority': 'CRITICAL',
            'issue': 'No active proxies',
            'recommendation': 'Configure proxy list in PROXY_LIST_STR'
        })

    # Analyze queue size
    queue_size = metrics.get('queue_size', 0)
    if queue_size > 500:
        recommendations.append({
            'priority': 'MEDIUM',
            'issue': f'Large queue size ({queue_size})',
            'recommendation': 'Check publishing performance, consider increasing publish interval'
        })

    # Analyze affiliate performance
    ctr = affiliate_stats.get('overall_ctr', 0)
    total_clicks = affiliate_stats.get('total_clicks', 0)
    if ctr < 0.5 and total_clicks > 10:
        recommendations.append({
            'priority': 'LOW',
            'issue': f'Low affiliate CTR ({ctr:.2f}%)',
            'recommendation': 'Review affiliate link quality, check ERID validity'
        })

    # Sort recommendations by priority
    priority_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    recommendations.sort(key=lambda x: priority_order.get(x['priority'], 4))

    # Print recommendations
    if recommendations:
        print(f"Found {len(recommendations)} optimization opportunities:")
        for rec in recommendations:
            print(f"\n[{rec['priority']}] {rec['issue']}")
            print(f"  -> {rec['recommendation']}")
    else:
        print("No optimization issues detected. System performing well!")

    return recommendations

async def run_performance_monitoring():
    """Run comprehensive performance monitoring"""
    print("Starting performance monitoring session...")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Monitor current performance
    result = await monitor_system_performance()
    if result:
        metrics, alerts, affiliate_stats = result
        recommendations = analyze_performance_data(metrics, alerts, affiliate_stats)

        # Performance score calculation
        parsing_score = min(100, metrics.get('parsing_success_rate', 100))
        proxy_score = min(100, metrics.get('avg_proxy_success_rate', 100))
        captcha_penalty = max(0, metrics.get('captcha_rate', 0) * 5)
        http_429_penalty = max(0, metrics.get('http_429_rate', 0) * 10)

        overall_score = max(0, (parsing_score + proxy_score) / 2 - captcha_penalty - http_429_penalty)

        print("\n=== PERFORMANCE SCORE ===")
        print(f"  Parsing Score: {parsing_score:.1f}/100")
        print(f"  Proxy Score: {proxy_score:.1f}/100")
        print(f"  CAPTCHA Penalty: -{captcha_penalty:.1f}")
        print(f"  HTTP 429 Penalty: -{http_429_penalty:.1f}")
        print(f"  Overall Score: {overall_score:.1f}/100")

        if overall_score >= 80:
            print("Status: EXCELLENT - System performing optimally")
        elif overall_score >= 60:
            print("Status: GOOD - Minor optimizations recommended")
        elif overall_score >= 40:
            print("Status: FAIR - Performance improvements needed")
        else:
            print("Status: POOR - Immediate attention required")

    else:
        print("Failed to collect performance metrics")

async def continuous_monitoring():
    """Run continuous monitoring with periodic reports"""
    print("Starting continuous performance monitoring...")
    print("Press Ctrl+C to stop")

    try:
        while True:
            await run_performance_monitoring()
            print("\n" + "="*60)
            print("Waiting 5 minutes for next check...")
            await asyncio.sleep(300)  # 5 minutes

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        # Continuous monitoring mode
        asyncio.run(continuous_monitoring())
    else:
        # Single monitoring run
        asyncio.run(run_performance_monitoring())
