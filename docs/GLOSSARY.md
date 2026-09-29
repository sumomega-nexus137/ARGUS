# Glossary — терминдер — терминология

Canonical operational terms as shown in the interface. The full catalogue is in
`frontend/messages/{kk,ru,en}.json`; `npm run i18n:check` enforces parity. Kazakh is the default language.

| Key | Қазақша | Русский | English |
|---|---|---|---|
| `health.PLAN_AT_RISK` | ЖОСПАР ҚАУІПТЕ | ПЛАН ПОД УГРОЗОЙ | PLAN AT RISK |
| `health.PLAN_VALID` | ЖОСПАР ОРЫНДАЛАДЫ | ПЛАН ВЫПОЛНИМ | PLAN VALID |
| `windows.latestStart` | ЕҢ КЕШ ҚАУІПСІЗ ШЫҒУ | ПОСЛЕДНИЙ БЕЗОПАСНЫЙ ВЫЕЗД | LATEST SAFE START |
| `windows.nextDecision` | КЕЛЕСІ МАҢЫЗДЫ ШЕШІМ | БЛИЖАЙШЕЕ КРИТИЧЕСКОЕ РЕШЕНИЕ | NEXT CRITICAL DECISION |
| `plan.stressTest` | ЖОСПАРДЫ СТРЕСС-ТЕСТІЛЕУ | СТРЕСС-ТЕСТ ПЛАНА | STRESS TEST PLAN |
| `plan.generate` | БАЛАМАЛАРДЫ ҚҰРУ | СФОРМИРОВАТЬ АЛЬТЕРНАТИВЫ | GENERATE ALTERNATIVES |
| `plan.gap` | РЕСУРС ТАПШЫЛЫҒЫ | ДЕФИЦИТ РЕСУРСОВ | RESOURCE GAP |
| `stress.robustness` | Орнықтылық | Устойчивость | Robustness |
| `common.why` | НЕГЕ? | ПОЧЕМУ? | WHY? |
| `optimizer.whyTask` | НЕГЕ БҰЛ ТАПСЫРМА? | ПОЧЕМУ ЭТА ЗАДАЧА? | WHY THIS TASK? |
| `optimizer.whyResource` | НЕГЕ БҰЛ РЕСУРС? | ПОЧЕМУ ЭТОТ РЕСУРС? | WHY THIS RESOURCE? |
| `optimizer.whyNow` | НЕГЕ ҚАЗІР? | ПОЧЕМУ СЕЙЧАС? | WHY NOW? |
| `optimizer.ifDelayed` | КЕШІКСЕ НЕ БОЛАДЫ? | ЧТО БУДЕТ ПРИ ЗАДЕРЖКЕ? | WHAT HAPPENS IF DELAYED? |
| `ops.recompute` | ҚАЙТА ЕСЕПТЕУ | ПЕРЕСЧИТАТЬ | RECOMPUTE |
| `data.conflictTitle` | ДЕРЕКТЕР ҚАЙШЫЛЫҒЫ | КОНФЛИКТ ДАННЫХ | DATA CONFLICT |
| `validation.notLoaded` | ВАЛИДАЦИЯ ДЕРЕКТЕРІ ЖҮКТЕЛМЕГЕН | ДАННЫЕ ДЛЯ ВАЛИДАЦИИ НЕ ЗАГРУЖЕНЫ | VALIDATION DATA NOT LOADED |
| `validation.iou` | IoU | IoU | IoU |
| `validation.precision` | Дәлдік | Точность | Precision |
| `validation.recall` | Толықтық | Полнота | Recall |
| `validation.curtain` | «Перде» арқылы салыстыру | Сравнение «шторкой» | Curtain comparison |
| `planStatus.DRAFT` | ЖОБА | ЧЕРНОВИК | DRAFT |
| `planStatus.REVIEWED` | ҚАРАЛДЫ | РАССМОТРЕН | REVIEWED |
| `planStatus.APPROVED` | БЕКІТІЛДІ | УТВЕРЖДЁН | APPROVED |
| `planStatus.ACTIVE` | ҚОЛДАНЫСТА | ДЕЙСТВУЕТ | ACTIVE |
| `policy.LIFE_SAFETY` | Адамдар қауіпсіздігі | Безопасность людей | Life safety |
| `policy.CRITICAL_INFRASTRUCTURE` | Аса маңызды инфрақұрылым | Критическая инфраструктура | Critical infrastructure |
| `policy.ECONOMIC_LOSS` | Экономикалық залал | Экономический ущерб | Economic loss |
| `policy.BALANCED` | Теңгерімді | Сбалансированная | Balanced |
| `plan.constraints` | Басшы шектеулері | Ограничения руководителя | Human constraints |
| `plan.template` | Бекітілген әрекет | Утверждённое действие | Approved action |
| `nav.bottlenecks` | Тар орындар | Узкие места | Bottlenecks |
| `road.CLOSED` | ЖАБЫҚ | ЗАКРЫТА | CLOSED |
| `road.RESTRICTED` | ШЕКТЕЛГЕН | ОГРАНИЧЕНА | RESTRICTED |
| `mode.SIMULATION` | СИМУЛЯЦИЯ | МОДЕЛИРОВАНИЕ | SIMULATION |
| `mode.LIVE` | ТІКЕЛЕЙ | ОНЛАЙН | LIVE |
| `mode.CACHED` | КЭШ | КЭШ | CACHED |
| `mode.HISTORICAL` | ТАРИХИ | АРХИВ | HISTORICAL |
| `roles.OPERATOR` | Оператор | Оператор | Operator |
| `roles.PLANNER` | Жоспарлаушы | Планировщик | Planner |
| `roles.COMMANDER` | Басшы | Руководитель | Commander |

## Concepts

* **Latest safe action time / соңғы қауіпсіз әрекет уақыты / последнее безопасное время действия** — the latest departure at which a task can still reach its site, work and leave before its window closes.
* **Action window** — interval before the earliest of: site flooding, crew egress loss, protected-road closure, explicit deadline.
* **Robustness** — share of stress-test perturbations in which no task fails. Not a probability.
* **Approved Action Library** — actions defined and approved by specialists; ARGUS only selects and schedules from them.
* **DEMO / SIMULATION** — synthetic data or clock; never presented as live measurements.
