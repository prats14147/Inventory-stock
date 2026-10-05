"""Allowlisted read capabilities available to the natural-language planner.

The model can choose a capability and propose filters. It cannot select a
Python function, provide SQL, or bypass the service layer.
"""

from dataclasses import dataclass

from app.nlp.intent import Intent


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    intent: Intent
    description: str
    required_arguments: tuple[str, ...] = ()
    optional_arguments: tuple[str, ...] = (
        "product_id", "store_id", "category", "start_date", "end_date", "group_by",
        "sort_order",
    )
    argument_types: tuple[tuple[str, str], ...] = (
        ("product_id", "catalog product ID string"),
        ("store_id", "catalog store ID string"),
        ("category", "known category string"),
        ("start_date", "ISO date string"),
        ("end_date", "ISO date string"),
        ("group_by", "total, product, store, or category"),
        ("sort_order", "ascending for least/lowest; descending for most/highest"),
    )
    backend_service: str = ""


TOOL_DEFINITIONS = (
    ToolDefinition("get_current_stock", Intent.CURRENT_STOCK, "Read current on-hand stock for a product or the whole inventory.", backend_service="inventory_service.get_product_inventory/get_current_inventory_listing"),
    ToolDefinition("get_low_stock", Intent.LOW_STOCK, "List product/store stock below the configured threshold.", backend_service="inventory_service.get_low_stock"),
    ToolDefinition("get_low_stock_fast_sellers", Intent.LOW_STOCK_FAST_SELLING, "Combine low-stock items with product sales velocity over the latest 30 days available in the sales data.", backend_service="inventory_service.get_low_stock + sales_service.get_top_products"),
    ToolDefinition("get_stock_history", Intent.STOCK_HISTORY, "Read the append-only stock movement ledger to explain when and why stock changed.", backend_service="stock_movements ledger"),
    ToolDefinition("get_sales_summary", Intent.SALES_TREND, "Summarize historical units sold over a time range.", backend_service="sales_service.get_sales_trend"),
    ToolDefinition("get_revenue", Intent.REVENUE_ANALYSIS, "Calculate recorded net sales revenue after discounts.", backend_service="sales_service.get_revenue_analysis"),
    ToolDefinition("get_gross_profit", Intent.FINANCIAL_ANALYSIS, "Calculate gross profit, COGS, and margin from sales transactions with saved costs.", backend_service="sales_service.get_profitability_analysis"),
    ToolDefinition("get_top_selling_products", Intent.TOP_SELLING, "Rank products by units sold.", backend_service="sales_service.get_top_products"),
    ToolDefinition("get_slow_selling_products", Intent.BOTTOM_SELLING, "Rank products by lowest units sold.", backend_service="sales_service.get_bottom_products"),
    ToolDefinition("get_category_analysis", Intent.CATEGORY_ANALYSIS, "Summarize unit sales by category.", backend_service="sales_service.get_category_analysis"),
    ToolDefinition("get_store_analysis", Intent.STORE_ANALYSIS, "Summarize unit sales by store.", backend_service="sales_service.get_store_analysis"),
    ToolDefinition("forecast_demand", Intent.DEMAND_FORECAST, "Forecast demand for one product.", required_arguments=("product_id",), backend_service="forecast_service.forecast_product_demand"),
    ToolDefinition("get_stockout_risk", Intent.STOCKOUT_RISK, "Calculate stockout risk for a product or all products.", backend_service="stockout_service.calculate_stockout_risk"),
    ToolDefinition("get_reorder_recommendation", Intent.REORDER_RECOMMENDATION, "Calculate how much to reorder for one product or all products.", backend_service="reorder_service.calculate_reorder"),
    ToolDefinition("get_product_info", Intent.PRODUCT_INFO, "Read product inventory and sales information.", required_arguments=("product_id",), backend_service="inventory_service.get_product_inventory + sales_service.get_sales_trend"),
)

TOOLS_BY_NAME = {tool.name: tool for tool in TOOL_DEFINITIONS}
TOOLS_BY_INTENT = {tool.intent: tool for tool in TOOL_DEFINITIONS}
