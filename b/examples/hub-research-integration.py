#!/usr/bin/env python3
"""
Example: Integrating Perplexity Research into The Hub

Use cases:
1. Validate if a scraped deal is actually good (market research)
2. Get context about trending products for newsletter
3. Verify pricing before alerting users
4. Research new products to add to scrapers
"""

import sys
sys.path.insert(0, '/Users/sydneyjackson/clawd')

from tools.research import research, research_deals, research_market_trends

def validate_deal(product_name: str, scraped_price: float, category: str = 'watches'):
    """
    Check if a scraped deal is actually good by researching market prices
    
    Returns: {
        'is_good_deal': bool,
        'market_price': str,
        'reasoning': str,
        'sources': list
    }
    """
    print(f"🔍 Researching market value for: {product_name}")
    
    result = research_deals(product_name, category=category, mode='fast')
    
    # Simple logic: extract if price mentioned in research
    # In production, you'd parse this more carefully
    is_good = 'deal' in result['content'].lower() or 'discount' in result['content'].lower()
    
    return {
        'is_good_deal': is_good,
        'market_context': result['content'][:500] + '...',  # First 500 chars
        'sources': result['citations'],
        'cost': result['cost']
    }

def get_trending_products(category: str = 'sneakers'):
    """
    Research what's hot in a category for newsletter content
    """
    print(f"📈 Researching trends in {category}...")
    
    result = research_market_trends(category, mode='fast')
    
    return {
        'trends': result['content'],
        'sources': result['citations'],
        'cost': result['cost']
    }

def research_new_product(product_name: str, category: str):
    """
    Research a product before adding it to scrapers
    - What's the typical price?
    - Where to find it?
    - What are red flags?
    """
    print(f"🆕 Researching new product: {product_name}")
    
    query = f"""
    Research {product_name} for resale/deal tracking:
    1. Typical retail and resale prices
    2. Best legitimate retailers/dealers
    3. Common scams or fakes
    4. Most desirable variants/models
    5. Seasonal pricing patterns
    """
    
    result = research(query, mode='fast')
    
    return {
        'product_guide': result['content'],
        'sources': result['citations'],
        'cost': result['cost']
    }

# Example Usage
if __name__ == '__main__':
    print("="*80)
    print("🔬 The Hub Research Integration Examples")
    print("="*80 + "\n")
    
    # Example 1: Validate a deal
    print("\n" + "─"*80)
    print("Example 1: Validate Deal")
    print("─"*80)
    validation = validate_deal("Rolex Submariner Date", 12000, category="watches")
    print(f"Good deal? {validation['is_good_deal']}")
    print(f"Market context: {validation['market_context']}")
    print(f"Cost: ${validation['cost']:.5f}")
    
    # Example 2: Get trending products
    print("\n" + "─"*80)
    print("Example 2: Trending Products")
    print("─"*80)
    trends = get_trending_products('sneakers')
    print(trends['trends'][:300] + "...")
    print(f"Sources: {len(trends['sources'])} citations")
    print(f"Cost: ${trends['cost']:.5f}")
    
    # Example 3: Research new product
    print("\n" + "─"*80)
    print("Example 3: Research New Product")
    print("─"*80)
    guide = research_new_product("Patek Philippe Nautilus 5711", "watches")
    print(guide['product_guide'][:300] + "...")
    print(f"Sources: {len(guide['sources'])} citations")
    print(f"Cost: ${guide['cost']:.5f}")
    
    print("\n" + "="*80)
    print("✅ Integration examples complete!")
    print("="*80)
