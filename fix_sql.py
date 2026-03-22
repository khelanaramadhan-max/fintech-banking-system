import re

with open('supabase-schema.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

def replacer(match):
    policy_name = match.group(1)
    table_name = match.group(2)
    return f'drop policy if exists "{policy_name}" on {table_name};\ncreate policy "{policy_name}" on {table_name}'

new_sql = re.sub(r'create policy\s+"([^"]+)"\s+on\s+([\w.]+)', replacer, sql)

with open('supabase-schema.sql', 'w', encoding='utf-8') as f:
    f.write(new_sql)
print('Fixed policies!')
