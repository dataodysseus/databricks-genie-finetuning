1) AGENT: SALES-KNOWLEDGE-ASSISTANT

This agent provides strategic business insights from internal documents including market research reports, product innovation plans, and store improvement strategies.

USE THIS AGENT FOR QUESTIONS ABOUT:
- Market trends and consumer behavior analysis
- Regional performance patterns and demographic preferences
- Product launch plans, innovation strategy, and new SKU details
- Store improvement initiatives and turnaround plans
- Competitive landscape and market positioning
- Strategic recommendations and business forecasts
- Qualitative insights, "why" questions, and context

DOCUMENT COVERAGE:
- Q4 2024 Market Analysis Report (market trends, top performers, regional analysis)
- 2025 Product Innovation Strategy (15 new launches, seasonal collections, regional customization)
- Store Performance Improvement Plan (8 underperforming stores, root causes, action plans)

EXAMPLE QUESTIONS THIS AGENT ANSWERS:
- What does our market research say about Q4 2024 performance?
- Which regions prefer which product types and why?
- What new products are launching in 2025?
- Which stores are underperforming and what are the specific issues?
- What's our competitive positioning strategy?
- Why do certain stores perform better than others?
- What are the strategic recommendations for 2025?

2) AGENT: SALES-DATA-AGENT (GENIE)

This agent provides quantitative analysis of real-time sales data from our transaction database, including revenue, customers, products, stores, and forecasts.

USE THIS AGENT FOR QUESTIONS ABOUT:
- Revenue metrics by any dimension (store, product, customer, time period)
- Transaction volumes, counts, and patterns
- Top/bottom performers by any metric (customers, products, stores)
- Sales distributions and value analysis
- Performance comparisons across dimensions
- Current and historical sales data
- Quantitative "what" and "how much" questions

DATA ACCESS:
- Sales transactions (2023-2025, daily granularity)
- 50 stores across United States
- 50 candy/confectionery products
- Customer transaction history
- Store locations and performance
- Product details and categories

EXAMPLE QUESTIONS THIS AGENT ANSWERS:
- Show me top 10 customers by revenue
- What's the revenue by product category?
- Which stores had the highest sales in Q4 2024?
- Calculate revenue trends by month
- Show distribution of total_sales_value
- What are the top products in Austin store?
- Compare revenue across different regions
- Show current month-to-date revenue

3) SQL_FUNCTION: GET-COMPETETOR-PRICE

   This tool provides real-time competitor pricing data from online retailers 
   including Walmart, Target, Amazon, Nike, and others.
   
   USE THIS TOOL WHEN:
   - Users ask about market prices for products
   - Users want competitor pricing information
   - Users need price comparison data
   - Users ask "how much do competitors charge"
   - Users want to know if our prices are competitive
   
   CAPABILITIES:
   - Returns real-time prices from major retailers
   - Provides average, minimum, and maximum prices
   - Covers wide range of product categories
   - Data from 10+ major US retailers
   
   EXAMPLE QUESTIONS:
   - What's the market price for chocolate bars?
   - How much do competitors charge for caramel products?
   - What are Nike shoes priced at in the market?
   - Compare our Choco Bliss ($4.20) to competitor prices
   - Are our prices competitive with the market?

4) SQL_FUNCTION: GET-RETAIL-NEWS

This tool searches Google News for breaking news, industry updates, and recent 
developments in retail, supply chain, and specific brands or product categories.

USE THIS TOOL WHEN:
- Users ask about recent news or current events
- Users want to know about industry announcements or trends
- Users need to understand market sentiment or developments
- Users ask "what's the latest news about..." or "recent updates on..."
- Users want competitor announcements or strategic moves
- Users need context about supply chain, pricing, or market changes

CAPABILITIES:
- Searches Google News for the most recent articles
- Returns top 5 news stories with headlines, sources, and dates
- Covers retail, candy, chocolate, supply chain, and market news
- Provides publication dates to assess recency
- Includes links to full articles for detailed reading

EXAMPLE QUESTIONS:
- What's the latest news about the candy industry?
- Are there any recent announcements from chocolate manufacturers?
- What's happening with retail supply chains this week?
- Show me recent news about chocolate pricing
- Find updates about holiday retail sales trends
- What are competitors announcing about new products?

INPUT PARAMETERS:
- query: The news topic to search (e.g., "chocolate industry", "retail supply chain")
- country: Two-letter country code (default: "us")

5) SQL_FUNCTION: GET-MARKET-TRENDS

This tool performs Google web searches to find market research, competitor 
strategies, industry trends, and general business intelligence about retail 
and product markets.

USE THIS TOOL WHEN:
- Users ask about market trends or industry analysis
- Users want information about competitor strategies or positioning
- Users need research on retail topics or market conditions
- Users ask "what are the trends..." or "how is the market..."
- Users want to understand industry best practices or benchmarks
- Users need context about market size, growth, or opportunities

CAPABILITIES:
- Searches the entire web via Google for comprehensive research
- Returns top 5 most relevant web results with summaries
- Provides article titles, descriptions, and source links
- Covers any topic: retail, candy, pricing, strategy, consumer behavior
- Finds market reports, analyst insights, and industry studies

EXAMPLE QUESTIONS:
- What are the latest trends in the candy industry for 2025?
- How is the premium chocolate market performing?
- What strategies are competitors using for online sales?
- What's the current state of retail e-commerce?
- Find information about candy pricing strategies
- What are consumer preferences for healthy snacks?

INPUT PARAMETERS:
- query: The search query (e.g., "candy market trends 2025")
- location: Geographic focus for results (default: "United States")

6) SQL_FUNCTION: FIND-COMPETITOR-LOCATIONS

This tool searches Google Maps to find physical store locations, analyze 
competitor density, and research local market presence for retail businesses 
in specific cities or regions.

USE THIS TOOL WHEN:
- Users ask about store locations in specific areas or cities
- Users want to analyze competitor presence or market density
- Users need to research local candy, chocolate, or retail stores
- Users ask "where are the stores..." or "how many competitors..."
- Users want geographic market intelligence or expansion insights
- Users need to understand local competitive landscape

CAPABILITIES:
- Searches Google Maps for businesses and retail locations
- Returns top 5 places with names, ratings, reviews, and addresses
- Provides customer ratings and review counts for each location
- Shows price level indicators when available
- Covers any geographic location (city, state, region, coordinates)

EXAMPLE QUESTIONS:
- How many candy stores are in Austin, Texas?
- Where are chocolate shops located in Manhattan?
- Show me competitor retail stores near Chicago
- What's the candy store density in Miami?
- Find specialty food stores in San Francisco
- Where can customers buy premium chocolate in Boston?

INPUT PARAMETERS:
- query: What to search for (e.g., "candy stores", "chocolate shops")
- location: The city, state, or area (e.g., "Austin, TX", "Manhattan, NY")

SQL_FUNCTION: GET-STORE-WEATHER

Get weather information for a store location based on its address or coordinates.
USE THIS TOOL WHEN:
- Users ask about current weather conditions at a store location
- Users want to understand how weather may impact store performance
- Users need weather context for sales analysis or planning
- Users ask "what's the weather..." or "current conditions at..."
- Users want temperature, precipitation, or forecast data
- Users need weather insights for specific dates or time periods
CAPABILITIES:
- Retrieves current weather data from a reliable weather API
- Provides temperature, humidity, wind speed, and conditions
- Offers forecast information for upcoming days
- Covers any geographic location based on address or coordinates
EXAMPLE QUESTIONS:
- What's the current weather at our Austin store?
- How's the weather looking for our Chicago location this weekend?
- Get temperature and conditions for our Miami store
- What's the forecast for our New York store next week?
- How might weather impact sales at our Denver location?
INPUT PARAMETERS:
- address: The store address (e.g., "123 Main St, Austin, TX")
- latitude: Latitude coordinate (optional)
- longitude: Longitude coordinate (optional)    