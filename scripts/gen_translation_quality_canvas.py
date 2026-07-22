"""Generate canvases/translation-quality.canvas.tsx from slim audit JSON."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLIM = json.loads(
    (ROOT / "data" / "oald" / "translation_quality_slim.json").read_text(encoding="utf-8")
)
OUT = Path(
    r"C:\Users\zattox\.cursor\projects\d-GITHUB-english-vocabulary-bot\canvases"
    r"\translation-quality.canvas.tsx"
)

cal = {
    "excellent": round(SLIM["counts"]["excellent"] * 0.90),
    "ok": round(SLIM["counts"]["ok"] + SLIM["counts"]["excellent"] * 0.08),
    "bad": round(SLIM["counts"]["bad"] + SLIM["counts"]["excellent"] * 0.10),
}
payload = {
    **SLIM,
    "calibrated": cal,
    "calibrated_note": (
        "После ручной калибровки выборки ~50 short excellent: "
        "~10% неверный/вторичный смысл."
    ),
}
data_js = json.dumps(payload, ensure_ascii=False)

tsx = f'''import {{
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  PieChart,
  Pill,
  Row,
  Spacer,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
  useHostTheme,
}} from "cursor/canvas";

const DATA = {data_js} as const;

type Tier = "excellent" | "ok" | "bad";

const TIER_LABEL: Record<Tier, string> = {{
  excellent: "Отлично",
  ok: "Средне",
  bad: "Ужасно",
}};

export default function TranslationQuality() {{
  const theme = useHostTheme();
  const [tier, setTier] = useCanvasState<Tier>("tier", "bad");

  const rows =
    tier === "excellent"
      ? DATA.excellent_sample.map((x) => [
          x.word,
          x.pos,
          x.main,
          (x.also || []).join(", "),
          x.cefr || "",
        ])
      : tier === "ok"
        ? DATA.ok.map((x) => [
            x.word,
            x.pos,
            x.main,
            (x.also || []).join(", "),
            (x.reasons || []).join(", "),
          ])
        : DATA.bad.map((x) => [
            x.word,
            x.pos,
            x.main,
            (x.also || []).join(", "),
            (x.definition || "").slice(0, 80),
          ]);

  const headers =
    tier === "excellent"
      ? ["Слово", "POS", "main", "also", "CEFR"]
      : tier === "ok"
        ? ["Слово", "POS", "main", "also", "Почему средне"]
        : ["Слово", "POS", "main", "also", "OALD definition"];

  return (
    <Stack gap={{24}} style={{{{ padding: 24, maxWidth: 1100 }}}}>
      <Stack gap={{8}}>
        <H1>Качество RU-переводов для студента</H1>
        <Text tone="secondary">
          Oxford 3000∪5000 · {{DATA.total}} карточек · source: data/oald/words.json
        </Text>
      </Stack>

      <Grid columns={{4}} gap={{16}}>
        <Stat value={{String(DATA.total)}} label="Всего" />
        <Stat
          value={{String(DATA.counts.excellent)}}
          label="Отлично (авто)"
          tone="success"
        />
        <Stat value={{String(DATA.counts.ok)}} label="Средне (авто)" tone="warning" />
        <Stat value={{String(DATA.counts.bad)}} label="Ужасно (авто)" tone="danger" />
      </Grid>

      <Callout tone="warning" title="Калибровка">
        {{DATA.caveat}} Оценка после ручной выборки: отлично ≈
        {{DATA.calibrated.excellent}}, средне ≈{{DATA.calibrated.ok}}, ужасно ≈
        {{DATA.calibrated.bad}}.
      </Callout>

      <Grid columns={{2}} gap={{20}}>
        <Card>
          <CardHeader>Авто-разметка</CardHeader>
          <CardBody>
            <PieChart
              data={{[
                {{ label: "Отлично", value: DATA.counts.excellent }},
                {{ label: "Средне", value: DATA.counts.ok }},
                {{ label: "Ужасно", value: DATA.counts.bad }},
              ]}}
              height={{220}}
            />
            <Text size="small" tone="secondary">
              Source: audit_translation_quality.py · form + known mismatches
            </Text>
          </CardBody>
        </Card>
        <Card>
          <CardHeader>После ручной калибровки</CardHeader>
          <CardBody>
            <BarChart
              categories={{["Отлично", "Средне", "Ужасно"]}}
              series={{[
                {{
                  name: "Оценка",
                  data: [
                    DATA.calibrated.excellent,
                    DATA.calibrated.ok,
                    DATA.calibrated.bad,
                  ],
                  tone: "info",
                }},
              ]}}
              height={{220}}
            />
            <Text size="small" tone="secondary">
              ~10% short glosses demoted from excellent after spot-check
            </Text>
          </CardBody>
        </Card>
      </Grid>

      <Stack gap={{8}}>
        <H2>Рубрика</H2>
        <Grid columns={{3}} gap={{12}}>
          <Card>
            <CardHeader>
              <Pill active tone="success">
                Отлично
              </Pill>
            </CardHeader>
            <CardBody>
              <Text>{{DATA.rubric.excellent}}</Text>
              <Spacer />
              <Text size="small" tone="secondary">
                Примеры: fear→страх, school→школа, accept→принимать
              </Text>
            </CardBody>
          </Card>
          <Card>
            <CardHeader>
              <Pill active tone="warning">
                Средне
              </Pill>
            </CardHeader>
            <CardBody>
              <Text>{{DATA.rubric.ok}}</Text>
              <Spacer />
              <Text size="small" tone="secondary">
                Примеры: mortgage→заклад (лучше ипотека), inspire→внушать
              </Text>
            </CardBody>
          </Card>
          <Card>
            <CardHeader>
              <Pill active tone="deleted">
                Ужасно
              </Pill>
            </CardHeader>
            <CardBody>
              <Text>{{DATA.rubric.bad}}</Text>
              <Spacer />
              <Text size="small" tone="secondary">
                Примеры: begin→она заплакала, spring→прыжок, spam→колбасный фарш
              </Text>
            </CardBody>
          </Card>
        </Grid>
      </Stack>

      <Divider />

      <Stack gap={{12}}>
        <H2>Просмотр по тирам</H2>
        <Row gap={{8}} wrap>
          {{(["bad", "ok", "excellent"] as const).map((t) => (
            <Pill key={{t}} active={{tier === t}} onClick={{() => setTier(t)}}>
              {{TIER_LABEL[t]}} (
              {{t === "excellent"
                ? DATA.excellent_sample.length + " sample"
                : t === "ok"
                  ? DATA.counts.ok
                  : DATA.counts.bad}}
              )
            </Pill>
          ))}}
        </Row>
        <Text size="small" tone="secondary">
          {{tier === "excellent"
            ? "Показана выборка из отличных (не все 5.6k)."
            : tier === "ok"
              ? "Все средне по авто-разметке."
              : "Все ужасные — править в первую очередь."}}
        </Text>
        <Table
          headers={{headers}}
          rows={{rows}}
          striped
          stickyHeader
          rowTone={{
            tier === "bad"
              ? rows.map(() => "danger" as const)
              : tier === "ok"
                ? rows.map(() => "warning" as const)
                : undefined
          }}
        />
      </Stack>

      <Stack gap={{8}}>
        <H3>Типичные причины (авто)</H3>
        <Table
          headers={{["Причина", "N"]}}
          rows={{DATA.top_reasons.map(([r, n]) => [r, String(n)])}}
          framed
        />
      </Stack>

      <Text size="small" tone="secondary" style={{{{ color: theme.text.secondary }}}}>
        Полный отчёт: data/oald/translation_quality_audit.json · скрипт:
        scripts/audit_translation_quality.py
      </Text>
    </Stack>
  );
}}
'''

OUT.write_text(tsx, encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
