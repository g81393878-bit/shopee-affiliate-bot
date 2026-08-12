-- บันทึกแคมเปญ (เอเจนต์ส่งโปรโมชั่น/สินค้าใหม่ตามหมวดที่ลูกค้าสนใจ)
create table if not exists campaign_logs (
    id bigserial primary key,
    category text not null,
    recipients integer not null default 0,
    status text not null default 'dryrun',
    created_at timestamptz not null default now()
);
