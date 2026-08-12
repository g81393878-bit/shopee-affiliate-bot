-- Chat logs: ประวัติสนทนากับลูกค้า (PDPA — เก็บ 90 วัน, ลูกค้าสั่งลบได้)
create table if not exists chat_logs (
    id bigserial primary key,
    line_user_id text not null,
    message_text text not null,
    intent text not null default 'unknown',
    reply_kind text not null default 'text',
    created_at timestamptz not null default now()
);
create index if not exists idx_chat_logs_user on chat_logs(line_user_id);
create index if not exists idx_chat_logs_created on chat_logs(created_at);
