-- Listing fields: a stable slug for each camp's URL, and spots left on each session.
-- Run after 0011_registration_alerts.sql. Additive; safe to re-run.

-- ---------------------------------------------------------------------------
-- camps.slug: the camp's address on the site (/camps/<slug>) and a readable key for people
-- and importers. It never changes when the name does, so links keep working.
-- ---------------------------------------------------------------------------
ALTER TABLE camps ADD COLUMN IF NOT EXISTS slug TEXT;

-- Real camps from data/camps/*.json keep their curated slug (their id is derived from it).
-- Generated from data/camps/*.json; tests/test_listing_fields.py checks the list is complete.
UPDATE camps c SET slug = v.slug
FROM (VALUES
    ('a9925037-92dc-530c-838a-460a408ec5ba'::uuid, 'beaver-summer-camp'),
    ('00a3c5e1-52c4-59a7-bba0-ee0d8e17cdc5'::uuid, 'belmont-day-camp'),
    ('37ec45f1-3fbd-5e67-bbb8-f6b7819f45fd'::uuid, 'camp-harbor-view'),
    ('84808320-62a5-58b6-b27c-a2c03488ad23'::uuid, 'camp-sewataro'),
    ('1daa7243-4561-597b-98de-4e0fa9bbec39'::uuid, 'camp-thayer'),
    ('029d4452-57a2-5d7c-9b56-0f58e6330f5f'::uuid, 'codman-community-farms-summer-barn-buddies'),
    ('ba0a3058-dbe4-5caa-8414-cbaa1128d77b'::uuid, 'crossroads-camp-wing-day-camp'),
    ('c82fd50f-7254-5c3c-8ecf-7534999aa781'::uuid, 'dexter-southfield-day-camp'),
    ('2f831eaa-1143-5677-9e3f-1e3a61f187c1'::uuid, 'fessenden-day-camp'),
    ('8a729984-a873-53f8-8d83-c5c191a6fe66'::uuid, 'hale-day-camp-westwood'),
    ('d9c6985d-9033-5c12-abf9-76d460aa2e3e'::uuid, 'hull-lifesaving-museum-summer-adventure'),
    ('3c445a91-7fcb-54c3-9a03-13835a906f0e'::uuid, 'jcc-camp-grossman'),
    ('3fac051c-7e07-586c-a6e8-a0f641b5a9f4'::uuid, 'mass-audubon-blue-hills-nature-camp'),
    ('1178703b-a2fc-529b-af0b-bdb7ca3ca94b'::uuid, 'mass-audubon-boston-nature-center-camp'),
    ('cbe6ce08-60d9-5465-a654-33876ed52d30'::uuid, 'mass-audubon-broadmoor-nature-camp'),
    ('906e5783-eb41-5a60-984d-21ce5b5590f7'::uuid, 'mass-audubon-drumlin-farm-camp'),
    ('85df681b-a9f4-5e6c-a82f-da48383c4ee8'::uuid, 'mass-audubon-habitat-nature-camp'),
    ('483a8414-90aa-5e98-ad82-0ef89874af75'::uuid, 'mass-audubon-ipswich-river-nature-camp'),
    ('cc0cd287-48e2-55ba-9589-3ac60b02761a'::uuid, 'mass-audubon-moose-hill-nature-camp'),
    ('df284307-8ab0-591b-ab86-76eab8f46ed2'::uuid, 'mass-audubon-stony-brook-nature-camp'),
    ('86e91ad1-5c59-5aa9-b2f7-c94e333ced14'::uuid, 'natick-community-organic-farm-summer-programs'),
    ('a807f5fb-17b8-5603-88a1-62209d18d4bf'::uuid, 'summer-at-bbn'),
    ('dd049d21-b75a-53a4-ad57-4785c68d1b9c'::uuid, 'tenacre-day-camp'),
    ('aabf3101-0ef9-5b83-b699-7b878cd4327b'::uuid, 'trustees-powisset-farm-farmer-forester-chef'),
    ('3e717071-930a-5a55-86ea-2d79ce1c5693'::uuid, 'trustees-weir-river-farm-camp'),
    ('ab567b2b-2f35-5550-ad0b-c378b01b6ac4'::uuid, 'trustees-worlds-end-camp'),
    ('f0f8efd1-3bdb-5615-b662-b49ddba5709f'::uuid, 'wsymca-camp-chickami'),
    ('652e2217-2479-5064-9df3-c87f2491b2e4'::uuid, 'wsymca-camp-pikati'),
    ('4c021461-cc64-518c-8bcd-a0712b9055f2'::uuid, 'ymca-burbank-day-camp'),
    ('03cb54a1-0b04-5226-9259-dad6361d22e6'::uuid, 'ymca-dorchester-day-camp'),
    ('e5d90bdf-1b89-56a4-acae-140c4264004c'::uuid, 'ymca-menino-day-camp'),
    ('566308c9-b401-5987-8c98-936d49e65389'::uuid, 'ymca-north-suburban-camp-nansema'),
    ('c45cbad3-b7f3-56ee-8ba3-0f7d8d38775a'::uuid, 'ymca-oak-square-camp-walsh'),
    ('06ca375d-9eab-581f-a4e2-e7ba606a574e'::uuid, 'ymca-parkway-day-camp'),
    ('32238671-865b-534d-ac9b-7c664c6bbf57'::uuid, 'ymca-waltham-cabot-day-camp'),
    ('4bf79d20-dc69-5725-b17a-c5da33748fbc'::uuid, 'behn-basketball-camp-babson-girls-overnight'),
    ('93b3a84a-5684-53d2-bf28-44b3b2099c5e'::uuid, 'cohen-camps-camp-pembroke'),
    ('f350ca23-3624-5a09-9e18-c6ea71f89839'::uuid, 'crossroads-camp-wing-overnight'),
    ('97f1ce2f-49bf-5cc5-a475-dc6775fa6835'::uuid, 'salvation-army-camp-wonderland'),
    ('e850b375-3dd4-5198-876f-c597684d8bde'::uuid, 'behn-basketball-camp-babson-day'),
    ('a505dc5d-f814-50ef-ba53-ee14b63780d1'::uuid, 'brookline-arts-center-summer-art-programs'),
    ('8c9436f1-2b47-5b05-a5e4-5ba86dab8fe4'::uuid, 'community-boating-junior-program'),
    ('e1abc437-e472-51bd-a3a3-0591108be4d7'::uuid, 'courageous-sailing-steps-to-lead-charlestown'),
    ('df676744-93d4-5c17-9e3d-6620c2cd53bb'::uuid, 'crs-summer-charles-river-creative-arts-program'),
    ('b83ad80f-cea5-5304-bad3-962937ad66c7'::uuid, 'dexter-southfield-scitech-camp'),
    ('c4c3192d-0edf-517f-adf5-b39e50538bc6'::uuid, 'hull-lifesaving-museum-summer-maritime-explorers'),
    ('0f72bf8d-ae49-58fd-b0e6-d9953d27ee39'::uuid, 'hull-yacht-club-learn-to-sail'),
    ('b75b86fb-603e-5eba-b56a-b8c932f514b6'::uuid, 'piers-park-sailing-center-summer-youth-programs'),
    ('5fa15957-6d96-55f9-99b7-0eb141322920'::uuid, 'tufts-childrens-theater'),
    ('52863406-f252-5a33-93b6-764d1de9231e'::uuid, 'audubon-summer-camp-bristol'),
    ('3e3779a4-3eff-529a-a7c1-433db88f73af'::uuid, 'barrington-recreation-cool-kids-camp-endeavor'),
    ('76550070-ff1e-5312-aa62-c909d2d30282'::uuid, 'boys-girls-club-east-providence-camp-crosby'),
    ('268e731b-573e-5331-89d4-7d6c5abae806'::uuid, 'boys-girls-clubs-warwick-norwood-steam-camp'),
    ('e81d5a42-cd43-5fe6-b052-586aeb780529'::uuid, 'boys-girls-clubs-warwick-oakland-beach-day-camp'),
    ('83ac7175-dcb8-52e2-abba-527c09ffb085'::uuid, 'camp-ramsbottom-rehoboth'),
    ('229310b2-0f69-5044-848b-b3f723340db2'::uuid, 'camp-riverside-taunton'),
    ('3c401296-fc1d-5f07-8d32-7f14e06eb208'::uuid, 'dwares-jcc-summer-j-camp'),
    ('194602e0-0f90-5743-823c-61b2b17eb6ef'::uuid, 'east-greenwich-rec-playground-camp-cole'),
    ('c3d448c2-148d-53b7-88e9-a50260342017'::uuid, 'east-greenwich-rec-playground-camp-eldredge'),
    ('006bab81-fb73-564b-8561-a0b86b7e2e43'::uuid, 'french-american-school-ri-summer-camp'),
    ('ce8dd06d-c6af-5c7e-ad40-121274425553'::uuid, 'gordon-school-summer-at-gordon'),
    ('53fdef4e-98f3-5222-b1dd-61316893bad5'::uuid, 'hockomock-ymca-camp-blackhawk-bellingham'),
    ('6440ae57-3a92-5ca5-b93b-764e0670306f'::uuid, 'hockomock-ymca-camp-elmwood-north-attleborough'),
    ('c13aeeed-ac18-5813-bb78-9afa8aa43944'::uuid, 'hockomock-ymca-camp-wapawca-foxborough'),
    ('362b1ed9-bcc6-5e22-a16f-ad7cefa23e43'::uuid, 'hockomock-ymca-camp-wiggi-franklin'),
    ('fb9b6247-b522-5a09-847e-2d48e4326219'::uuid, 'moses-brown-rise-camp'),
    ('5d99d3df-86f9-5305-b616-2c1f15a73527'::uuid, 'newman-ymca-summer-day-camp-seekonk'),
    ('1cee93da-f5b9-5899-bc28-1f5482406d2a'::uuid, 'norman-bird-sanctuary-summer-camp'),
    ('90ac86cd-d1fb-5f30-a0d9-669f743cf8d1'::uuid, 'providence-country-day-summer-at-pcd'),
    ('3b943a79-dad6-59a1-94b8-cfb2fbb68eeb'::uuid, 'rocky-hill-camp-east-greenwich'),
    ('7a972e7b-26ad-5421-ad5d-c5afd01b2c47'::uuid, 'roger-williams-park-zoo-zoocamp'),
    ('b56c2654-95ae-54a3-8faf-8021ec0bb480'::uuid, 'save-the-bay-baycamp-providence'),
    ('a2cc1e51-bb8f-5db5-987b-9fab2a072d67'::uuid, 'summer-at-st-andrews-barrington'),
    ('a7f3e796-3acb-547b-97a7-701edb723524'::uuid, 'wheeler-summer-camp-seekonk'),
    ('266ba041-f3cb-5878-a669-b41b8d4ed40e'::uuid, 'ymca-greater-providence-bayside-camp-manitoo'),
    ('e3316f97-972d-5804-b1f4-309bba64b4c9'::uuid, 'ymca-greater-providence-cranston-day-camp'),
    ('60551dbf-8fa8-5883-887e-6efc8480a62f'::uuid, 'ymca-greater-providence-kent-county-day-camp'),
    ('6d8eb839-5eda-5b7b-82fe-8f61f61b8abb'::uuid, 'ymca-greater-providence-south-county-day-camp'),
    ('5aebd81e-dc86-576e-86d0-e3862bb5f0f3'::uuid, 'ymca-southcoast-camp-quequechan-fall-river'),
    ('ec6a1b44-0190-5819-b1a3-36db9c39b28d'::uuid, 'ymca-southcoast-camp-weetamoe-swansea'),
    ('9b9c3e7d-5415-5bd0-b4ca-0faf55cbbee7'::uuid, 'camp-aldersgate-overnight'),
    ('9a26e52e-5426-59fa-a813-03dbbc529a5c'::uuid, 'camp-jori-overnight'),
    ('b00380bc-d3cd-5fb1-a1cb-a05fef8399e6'::uuid, 'girl-scouts-camp-hoffman'),
    ('c449c0bc-c7ef-5ac1-87a2-9344beb7167a'::uuid, 'ymca-camp-fuller'),
    ('3307b42c-39bf-5cda-aafc-4ee7a7c8db84'::uuid, 'attleboro-arts-museum-summer-art-weeks'),
    ('05441c8d-d3e3-57c6-b642-d2083f237cb4'::uuid, 'bryant-university-bulldog-youth-soccer-camp'),
    ('4bb4abc2-5b48-5dff-acad-8b83d1650ecc'::uuid, 'capron-park-zoo-summer-outdoor-adventures'),
    ('3baec17a-1fdc-5173-b015-ada01a59cd0c'::uuid, 'community-boating-center-providence-summer-camp'),
    ('201d853e-d745-5157-9549-8f74725beecb'::uuid, 'dean-summer-arts-institute'),
    ('92caf794-0fea-5b2c-9834-0ebafb5a8561'::uuid, 'east-bay-sailing-foundation-junior-sailing'),
    ('f2466b0d-2e8a-54c1-afb8-024fd18ee608'::uuid, 'edgewood-sailing-school-youth'),
    ('092134c3-0c8d-55ca-959e-a57a9ebfb66c'::uuid, 'herreshoff-marine-museum-youth-sailing-camp'),
    ('113d77ea-c609-57b4-937f-11a9b67f19b6'::uuid, 'hockomock-ymca-mansfield-theatre-production-camp'),
    ('43b10955-45ba-52ca-b598-dd93379dcaca'::uuid, 'resendes-soccer-academy-bryant-summer-camp'),
    ('e3b0f851-ac42-5a28-9e1c-b68f72d1d9c8'::uuid, 'sam-lopes-soccer-academy-providence-college-youth-camp'),
    ('f24ddec9-ecd3-5954-939f-1a3b28e43f14'::uuid, 'uri-sailing-center-youth-summer-sailing')
) AS v(id, slug)
WHERE c.id = v.id AND c.slug IS NULL
  AND NOT EXISTS (SELECT 1 FROM camps o WHERE o.slug = v.slug);

-- Every other camp: name and town, e.g. riverside-soccer-camp-providence. A clash gets the
-- first 8 characters of the id added.
WITH base AS (
    SELECT id, trim(both '-' FROM regexp_replace(lower(name || '-' || coalesce(city, '')), '[^a-z0-9]+', '-', 'g')) AS s
    FROM camps WHERE slug IS NULL
), numbered AS (
    SELECT id, s, row_number() OVER (PARTITION BY s ORDER BY id) AS n FROM base
)
UPDATE camps c
SET slug = CASE WHEN numbered.n = 1 AND NOT EXISTS (SELECT 1 FROM camps o WHERE o.slug = numbered.s)
                THEN numbered.s ELSE numbered.s || '-' || left(c.id::text, 8) END
FROM numbered WHERE c.id = numbered.id;

-- New camps get the same name-and-town slug unless the insert sets one.
CREATE OR REPLACE FUNCTION camps_default_slug() RETURNS trigger LANGUAGE plpgsql AS '
BEGIN
    IF NEW.slug IS NULL OR NEW.slug = '''' THEN
        NEW.slug := trim(both ''-'' FROM regexp_replace(lower(NEW.name || ''-'' || coalesce(NEW.city, '''')), ''[^a-z0-9]+'', ''-'', ''g''));
        IF EXISTS (SELECT 1 FROM camps WHERE slug = NEW.slug AND id <> NEW.id) THEN
            NEW.slug := NEW.slug || ''-'' || left(NEW.id::text, 8);
        END IF;
    END IF;
    RETURN NEW;
END';
DROP TRIGGER IF EXISTS trg_camps_default_slug ON camps;
CREATE TRIGGER trg_camps_default_slug BEFORE INSERT ON camps
    FOR EACH ROW EXECUTE FUNCTION camps_default_slug();

ALTER TABLE camps ALTER COLUMN slug SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS camps_slug_idx ON camps (slug);

-- ---------------------------------------------------------------------------
-- sessions: spots left, with when and from whom. Null means we don't know, which is
-- different from 0 (full). availability stays the coarse open / waitlist / full status.
-- ---------------------------------------------------------------------------
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS spots_total      INTEGER CHECK (spots_total >= 0);
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS spots_available  INTEGER CHECK (spots_available >= 0);
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS spots_updated_at TIMESTAMPTZ;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS spots_source     TEXT CHECK (spots_source IN ('owner', 'team', 'import'));

DO '
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = ''sessions_spots_within_total'') THEN
        ALTER TABLE sessions ADD CONSTRAINT sessions_spots_within_total
            CHECK (spots_available IS NULL OR spots_total IS NULL OR spots_available <= spots_total);
    END IF;
END';
