-- shopee_products staging table: raw products pulled from Shopee Affiliate Open API
-- (productOfferV2 nodes). Separate from `products` (curated list the LINE bot answers with).
-- Fetched in bulk (tens of thousands); curated picks get promoted into `products`.

create extension if not exists pg_trgm;

create table if not exists shopee_products (
  id                    bigserial primary key,
  item_id               bigint not null unique,          -- Shopee item id
  shop_id               bigint,                          -- Shopee shop id
  shop_name             text,
  product_name          text not null,
  product_link          text,
  offer_link            text,                            -- link already carrying affiliate tracking
  image_url             text,
  price_min             numeric(12, 2),
  price_max             numeric(12, 2),
  price_discount_rate   double precision,
  sales                 integer,
  rating_star           double precision,
  commission_rate       text,                            -- e.g. "0.0850" = 8.5% (string from API)
  seller_commission_rate text,
  shopee_commission_rate text,
  commission            numeric(12, 2),                  -- estimated commission
  shop_type             integer,
  category_id           bigint,
  period_start_time     bigint,
  period_end_time       bigint,
  raw_json              jsonb,                           -- full API node for later fields
  fetched_at            timestamptz not null default now()
);

create index if not exists idx_shopee_products_item_id on shopee_products (item_id);
create index if not exists idx_shopee_products_shop_id on shopee_products (shop_id);
create index if not exists idx_shopee_products_name_trgm on shopee_products using gin (product_name gin_trgm_ops);
