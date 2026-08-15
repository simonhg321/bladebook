#!/usr/bin/env python3
"""bladebook example seed — four fictional knives exercising the schema
(folder + fixed, damascus, inlay, left-handed, for-sale). Idempotent;
re-run any time to reset the example data to this baseline.
Run: python3 scripts/seed_example.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bladebook import db  # noqa: E402

EXAMPLE = [
    ('K01', dict(family='Sebenza', model='Sebenza', generation='31',
                 size='Large', blade_shape='Drop Point'), dict(
        crk_sku='L31-0000', steel='MagnaCut', hardness_note='63-64 RC',
        handle_treatment='plain-ti', born_on='2024-06-01',
        has_box=1, has_card=1, notes_public='Example knife — plain titanium.',
        hero_photo=None)),
    ('K02', dict(family='Sebenza', model='Sebenza', generation='31',
                 size='Small', blade_shape='Insingo'), dict(
        steel='Damascus', hardness_note='57-58 RC',
        damascus_smith='Example Smith', damascus_pattern='Stainless Ladder',
        handle_treatment='inlay', inlay_material='box elder burl',
        hand='left', born_on='2023-02-14', has_box=1, has_card=1,
        notes_public='Example knife — damascus, left-handed.', hero_photo=None)),
    ('K03', dict(family='Inkosi', model='Inkosi', size='Large',
                 blade_shape='Drop Point'), dict(
        steel='S45VN', hardness_note='61-62 RC', surface_finish='cerakote',
        born_on='2022-11-30', has_box=1,
        sale_status='for_sale', asking_price=450,
        notes_public='Example knife — marked for sale/trade.', hero_photo=None)),
    ('K04', dict(family='Fixed Blade', model='Backpacker',
                 knife_type='fixed', blade_shape='Drop Point'), dict(
        steel='MagnaCut', hardness_note='63-64 RC', born_on='2025-01-15',
        notes_public='Example knife — fixed blade.', hero_photo=None)),
]


def main():
    con = db.connect()
    with con:
        for tag, model_fields, knife_fields in EXAMPLE:
            mid = db.upsert_model(con, **model_fields)
            kid = db.upsert_knife(con, tag, model_id=mid, **knife_fields)
            if not any(e['type'] == 'photographed'
                       for e in db.list_events(con, kid)):
                db.add_event(con, kid, knife_fields.get('born_on'),
                             'photographed', detail='example intake')
    print(f'seeded {len(EXAMPLE)} knives into {db._path()}')
    for k in db.list_knives(con):
        print(f"  {k['tag']}  {k['size'] or ''} {k['family']} "
              f"{k['generation'] or ''}  born {k['born_on']}")
    con.close()


if __name__ == '__main__':
    main()
