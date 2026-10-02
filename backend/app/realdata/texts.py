"""Kazakh / Russian renderings of the builder's and the packs' explanatory English text.

The English sentence stays the authoritative source string (it is what the pack or the builder wrote); the UI picks
the active locale and falls back to English for any sentence without a rendering here."""

from __future__ import annotations

# english → (kk, ru)
TR: dict[str, tuple[str, str]] = {
    # area assumptions (build._assumptions)
    "Operational speed caps by OSM class (km/h); OSMnx-imputed speeds are capped.": (
        "OSM жол класы бойынша жедел жылдамдық шектері (км/сағ); OSMnx бағалаған жылдамдықтар осы шектермен шектеледі.",
        "Оперативные ограничения скорости по классу дорог OSM (км/ч); скорости, оценённые OSMnx, ограничиваются ими."),
    "Emergency vehicles may use one-way streets in both directions.": (
        "Төтенше қызмет көліктері біржақты көшелермен екі бағытта да жүре алады деп қабылданған.",
        "Принято, что аварийно-спасательный транспорт может двигаться по улицам с односторонним движением в обоих направлениях."),
    "Road surface assumed at DEM ground level (no embankment survey).": (
        "Жол беті DEM жер деңгейінде деп қабылданған (үйінді биіктігі өлшенбеген).",
        "Покрытие дороги принято на уровне земли по DEM (съёмка насыпей отсутствует)."),
    "Assumed deck clearance above the river proxy level (no survey).": (
        "Көпір аралығының өзен деңгейі проксиінен биіктігі болжамды (өлшеу жүргізілмеген).",
        "Принятый подмостовой габарит над прокси-уровнем реки (без обследования)."),
    "ARGUS default policy by type — requires specialist review.": (
        "Нысан түрі бойынша ARGUS әдепкі саясаты — маман тексеруін қажет етеді.",
        "Политика ARGUS по умолчанию по типу объекта — требует проверки специалистом."),
    "Sectors are analysis grid cells, not administrative boundaries.": (
        "Секторлар — талдау торының ұяшықтары, әкімшілік шекаралар емес.",
        "Секторы — ячейки аналитической сетки, а не административные границы."),
    "No verified agency inventory: crews, vehicles, pumps and equipment are SIMULATION.": (
        "Ведомстволардың расталған тізілімі жоқ: топтар, көліктер, сорғылар мен техника — СИМУЛЯЦИЯ.",
        "Нет подтверждённого ведомственного реестра: расчёты, транспорт, насосы и техника — МОДЕЛИРОВАНИЕ."),
    "No approved regional valuation table: exposure is reported as floor area, no money.": (
        "Бекітілген өңірлік бағалау кестесі жоқ: әсер ақшамен емес, еден ауданымен көрсетіледі.",
        "Нет утверждённой региональной таблицы стоимости: воздействие показано площадью помещений, без денежной оценки."),
    # scenario names
    "Atbasar 2024 — historical reconstruction (LOW / BASE / HIGH)": (
        "Атбасар 2024 — тарихи қайта құру (LOW / BASE / HIGH)",
        "Атбасар 2024 — историческая реконструкция (LOW / BASE / HIGH)"),
    "Kokshetau — Kylshakty exercise scenario on real terrain (SIMULATION)": (
        "Көкшетау — нақты жер бедеріндегі Қылшақты жаттығу сценарийі (СИМУЛЯЦИЯ)",
        "Кокшетау — учебный сценарий Кылшакты на реальном рельефе (МОДЕЛИРОВАНИЕ)"),
    # Atbasar scenario note / limitations
    ("Hybrid terrain-conditioned susceptibility and stage proxy calibrated against the Sentinel-2 flood evidence "
     "of 14 Apr 2024. Not a hydrodynamic model. Time profile is a stage-proxy presentation; the peak (offset 0) "
     "is anchored to the official overflow record of 11 Apr 2024 04:43 (Zhabai 5.95 m local level). Native "
     "frames every 180 min; intermediate frames are linear interpolations."): (
        "2024 жылғы 14 сәуірдегі Sentinel-2 су басу деректері бойынша калибрленген, жер бедеріне негізделген гибридті "
        "сезімталдық және деңгей проксиі. Гидродинамикалық модель емес. Уақыттық профиль — деңгей проксиінің көрінісі; "
        "шың (0 ығысу) 2024 жылғы 11 сәуір 04:43-тегі ресми асып төгілу жазбасына байланған (Жабай, жергілікті деңгей "
        "5,95 м). Негізгі кадрлар әр 180 минут сайын; аралық кадрлар — сызықтық интерполяция.",
        "Гибридная модель восприимчивости с учётом рельефа и прокси уровня, откалиброванная по данным Sentinel-2 о "
        "затоплении на 14.04.2024. Не гидродинамическая модель. Временной профиль — представление прокси уровня; пик "
        "(смещение 0) привязан к официальной записи о переливе 11.04.2024 04:43 (Жабай, местный уровень 5,95 м). "
        "Исходные кадры через 180 мин; промежуточные — линейная интерполяция."),
    ("Town-interior flooding from embankment overtopping (officially recorded on 11 Apr 2024) is not reproduced: "
     "the 30 m DSM does not resolve levees/culverts and the 14 Apr optical mask shows no detectable open water in the built-up area."): (
        "Бөгеттен асып төгілуден болған қала ішінің су басуы (2024 жылғы 11 сәуірде ресми тіркелген) қайталанбайды: "
        "30 м DSM бөгеттер мен су өткізгіштерді ажыратпайды, ал 14 сәуірдегі оптикалық маска құрылыс аумағында ашық суды көрсетпейді.",
        "Затопление внутри города из-за перелива через дамбу (официально зафиксировано 11.04.2024) не воспроизводится: "
        "ЦМП 30 м не разрешает дамбы и водопропуски, а оптическая маска на 14.04 не показывает открытой воды в застройке."),
    # pack scientific limitations (calibration_metrics.json)
    "This is a hybrid terrain/susceptibility model, not HEC-RAS/LISFLOOD-FP or a surveyed hydraulic model.": (
        "Бұл — жер бедері/сезімталдықтың гибридті моделі, HEC-RAS/LISFLOOD-FP немесе өлшеуге негізделген гидравликалық модель емес.",
        "Это гибридная модель рельефа/восприимчивости, а не HEC-RAS/LISFLOOD-FP и не гидравлическая модель по данным съёмки."),
    "The same historical event supplies the satellite target; the alternating spatial holdout is not out-of-event validation.": (
        "Спутниктік эталон сол тарихи оқиғадан алынған; кезектесетін кеңістіктік бөлу басқа оқиға бойынша тексеру емес.",
        "Спутниковый эталон взят из того же исторического события; чередующаяся пространственная отложенная выборка "
        "не является проверкой на другом событии."),
    "The susceptibility classifier uses terrain/hydro features only and intentionally excludes raw X/Y coordinates.": (
        "Сезімталдық классификаторы тек жер бедері/гидрологиялық белгілерді пайдаланады және X/Y координаттарын әдейі қоспайды.",
        "Классификатор восприимчивости использует только признаки рельефа/гидрологии и намеренно исключает координаты X/Y."),
    "DEM is a ~30 m DSM and local levees/culverts/channel bathymetry are not surveyed here.": (
        "DEM — шамамен 30 м DSM; жергілікті бөгеттер, су өткізгіштер және арна батиметриясы өлшенбеген.",
        "DEM — ЦМП ~30 м; местные дамбы, водопропуски и батиметрия русла не обследованы."),
    ("Gauge stage and the stage proxy are related only for scenario presentation; this is not a validated "
     "stage-discharge-depth rating curve."): (
        "Бекет деңгейі мен деңгей проксиі тек сценарийді көрсету үшін байланыстырылған; бұл расталған деңгей–шығын–тереңдік қисығы емес.",
        "Уровень поста и прокси уровня связаны только для представления сценария; это не проверенная кривая уровень–расход–глубина."),
    "Observed satellite mask remains subject to manual/domain QC.": (
        "Бақыланған спутниктік маска әлі де қолмен/сала маманының сапа бақылауын қажет етеді.",
        "Наблюдённая спутниковая маска по-прежнему требует ручного/экспертного контроля качества."),
    # Kokshetau scenario note / limitations
    "Kokshetau — Kylshakty historically bounded operational exercise (SIMULATION)": (
        "Көкшетау — Қылшақты: тарихи әсер ауқымымен шектелген операциялық жаттығу (СИМУЛЯЦИЯ)",
        "Кокшетау — Кылшакты: оперативные учения, ограниченные историческим масштабом последствий (СИМУЛЯЦИЯ)"),
    ("SIMULATION exercise on real Kokshetau terrain. The earlier broad stage-HAND envelope was replaced by a "
     "conservative 100 m river-connected corridor and LOW/BASE/HIGH excess stages of 0.10/0.20/0.40 m. "
     "The BASE exercise is bounded only to the order of magnitude of the officially reported 2024 impacts "
     "(16 private houses, 29 private yards, 12 apartment courtyards and the first floor of Ertostik kindergarten). "
     "Those reported categories are NOT equivalent to modelled building footprints, so this is not a historical "
     "inundation reconstruction or forecast validation. Use it to exercise access/bottleneck consequences on real geography. "
     "Lake Kopa remains downstream receiving water, not the assumed flood cause."): (
        "Көкшетаудың нақты жер бедеріндегі СИМУЛЯЦИЯ жаттығуы. Бұрынғы кең stage-HAND аумағы өзенмен байланысқан "
        "консервативті 100 м дәлізге және LOW/BASE/HIGH үшін 0,10/0,20/0,40 м артық деңгейлерге ауыстырылды. "
        "BASE жаттығуы 2024 жылғы ресми хабарланған әсердің тек шамалық ауқымымен шектелген "
        "(16 жеке үй, 29 жеке аула, 12 көпқабатты үй ауласы және «Ертөстік» балабақшасының бірінші қабаты). "
        "Бұл санаттар модельдегі ғимарат іздерімен тең емес, сондықтан бұл тарихи су басуды қалпына келтіру де, "
        "болжамды валидациялау да емес. Нақты географияда қолжетімділік пен тар орындардың салдарын жаттықтыру үшін қолданылады. "
        "Қопа көлі төменгі ағыстағы қабылдаушы су болып қалады, болжамды су басу себебі емес.",
        "СИМУЛЯЦИОННЫЕ учения на реальном рельефе Кокшетау. Прежняя широкая область stage-HAND заменена "
        "консервативным 100-метровым коридором, связанным с рекой, и превышениями уровня LOW/BASE/HIGH "
        "0,10/0,20/0,40 м. BASE ограничен только порядком масштаба официально сообщённых последствий 2024 года "
        "(16 частных домов, 29 частных дворов, 12 дворов многоквартирных домов и первый этаж детсада «Ертөстік»). "
        "Эти категории не эквивалентны модельным контурам зданий, поэтому это не реконструкция исторического затопления "
        "и не валидация прогноза. Сценарий предназначен для отработки доступа и узких мест на реальной географии. "
        "Озеро Копа остаётся водоприёмником ниже по течению, а не предполагаемой причиной паводка."),
    "Historically impact-bounded SIMULATION, not a spatially calibrated flood extent and not a prediction of which property will flood.": (
        "Тарихи әсер ауқымымен шектелген СИМУЛЯЦИЯ; кеңістіктік калибрленген су басу аумағы емес және қай нысанды су басатыны туралы болжам емес.",
        "СИМУЛЯЦИЯ, ограниченная историческим масштабом последствий; это не пространственно откалиброванная зона затопления и не прогноз конкретных затапливаемых объектов."),
    "Static stage–HAND approximation, not a hydraulic model; no surveyed culvert/bridge/channel hydraulics.": (
        "Статикалық stage–HAND жуықтауы, гидравликалық модель емес; су өткізгіштер, көпірлер мен арнаның өлшенген гидравликасы жоқ.",
        "Статическое приближение stage–HAND, не гидравлическая модель; нет обследованной гидравлики водопропусков, мостов и русла."),
    "The 100 m Kylshakty corridor is a conservative ARGUS exercise envelope, not an official flood-zone boundary.": (
        "Қылшақты бойындағы 100 м дәліз — ARGUS-тың консервативті жаттығу шекарасы, ресми су басу аймағының шекарасы емес.",
        "100-метровый коридор вдоль Кылшакты — консервативная граница учений ARGUS, а не официальная граница зоны затопления."),
    "30 m DSM: buildings/trees bias terrain; urban drainage, frozen-ground runoff and snowmelt ponding are not explicitly resolved.": (
        "30 м DSM: ғимараттар мен ағаштар жер бедерін бұрмалайды; қалалық дренаж, тоң топырақтағы ағын және еріген қар суының жиналуы нақты есептелмейді.",
        "ЦМП 30 м: здания и деревья искажают рельеф; городской дренаж, сток по промёрзшему грунту и накопление талых вод явно не разрешаются."),
    "Official Kylshakty levels use an unestablished gauge datum and are not used as a direct model stage.": (
        "Қылшақтының ресми деңгейлері белгіленбеген пост нөліне қатысты берілген және модель деңгейі ретінде тікелей қолданылмайды.",
        "Официальные уровни Кылшакты относятся к неустановленному нулю поста и не используются напрямую как уровень модели."),
    ("SIMULATION exercise: water level above the Kylshakty channel (m) applied to real terrain with river connectivity. "
     "NOT calibrated — no observed flood extent exists for Kokshetau in the packs. On the 30 m DSM the proxy "
     "OVERESTIMATES exposure compared with the officially reported 2024 impact (16 private houses, 29 yards, "
     "12 apartment courtyards, one kindergarten floor); use it for network/bottleneck exercises only. "
     "Lake Kopa is treated as downstream receiving water, not as a flood cause."): (
        "СИМУЛЯЦИЯ жаттығуы: Қылшақты арнасынан жоғары су деңгейі (м) өзенмен байланысы ескеріліп нақты жер бедеріне "
        "қолданылады. КАЛИБРЛЕНБЕГЕН — пакеттерде Көкшетау үшін бақыланған су басу аумағы жоқ. 30 м DSM-де прокси 2024 "
        "жылғы ресми тіркелген әсерге (16 жеке үй, 29 аула, 12 көппәтерлі үй ауласы, балабақшаның бір қабаты) қарағанда "
        "әсерді АРТЫҚ бағалайды; тек жол желісі мен тар орындар жаттығулары үшін пайдаланыңыз. Қопа көлі су басу себебі "
        "емес, төменгі ағыстағы қабылдаушы су ретінде қарастырылады.",
        "Учения (МОДЕЛИРОВАНИЕ): уровень воды над руслом Кылшакты (м) применён к реальному рельефу с учётом связности "
        "с рекой. НЕ откалибровано — в пакетах нет наблюдённой зоны затопления для Кокшетау. На ЦМП 30 м прокси "
        "ЗАВЫШАЕТ воздействие по сравнению с официально зарегистрированным в 2024 г. (16 частных домов, 29 дворов, "
        "12 дворов многоквартирных домов, один этаж детского сада); используйте только для учений по дорожной сети и "
        "узким местам. Озеро Копа рассматривается как водоприёмник ниже по течению, а не как причина паводка."),
    "Static stage–HAND approximation, not a hydraulic model; no culvert/bridge hydraulics.": (
        "Статикалық деңгей–HAND жуықтауы, гидравликалық модель емес; су өткізгіш пен көпір гидравликасы есептелмейді.",
        "Статическое приближение уровень–HAND, не гидравлическая модель; гидравлика водопропусков и мостов не моделируется."),
    "30 m DSM: buildings/trees bias terrain; urban drainage and snowmelt ponding are not represented.": (
        "30 м DSM: ғимараттар мен ағаштар жер бедерін бұрмалайды; қалалық дренаж бен қар суының жиналуы ескерілмеген.",
        "ЦМП 30 м: здания и деревья искажают рельеф; городской дренаж и застой талых вод не учитываются."),
    "Official Kylshakty levels use an unestablished gauge datum and are not used for conditioning.": (
        "Қылшақтының ресми деңгейлері белгіленбеген нөлдік белгіге негізделген және сценарийді түзетуге пайдаланылмайды.",
        "Официальные уровни Кылшакты даны от неустановленного нуля поста и не используются для корректировки сценария."),
    # official chronology (pack curated events)
    "Warning: rapid snowmelt/runoff and breakup on Zhabai/Kalkutan expected 3-6 Apr; levels may reach/exceed critical marks.": (
        "Ескерту: 3–6 сәуірде Жабай/Қалқұтан өзендерінде қардың қарқынды еруі, ағын және мұз жүруі күтіледі; деңгейлер "
        "сыни белгілерге жетуі немесе асуы мүмкін.",
        "Предупреждение: 3–6 апреля на Жабае/Калкутане ожидаются интенсивное снеготаяние, сток и вскрытие; уровни могут "
        "достичь или превысить критические отметки."),
    ("Residents of coastal zones of Ishim, Zhabai and Zhylandy warned that critical levels were expected within the next day "
     "and to prepare for evacuation."): (
        "Есіл, Жабай және Жыланды өзендерінің жағалау аймақтарының тұрғындарына келесі тәулік ішінде сыни деңгейлер "
        "күтілетіні және эвакуацияға дайындалу қажеттігі ескертілді.",
        "Жители прибрежных зон Ишима, Жабая и Жыланды предупреждены, что критические уровни ожидаются в течение суток, "
        "и о необходимости готовиться к эвакуации."),
    "123 people reported evacuated; 133 responders/participants, 38 equipment units and 10 motor pumps involved.": (
        "123 адам эвакуацияланғаны хабарланды; 133 қатысушы/құтқарушы, 38 техника бірлігі және 10 мотопомпа тартылды.",
        "Сообщается об эвакуации 123 человек; задействованы 133 участника, 38 единиц техники и 10 мотопомп."),
    "Overflow occurred at six sections of the earth embankment on the Zhabai, leading to flooding in Atbasar.": (
        "Жабайдағы топырақ бөгеттің алты учаскесінде су асып төгіліп, Атбасарда су басу болды.",
        "Произошёл перелив на шести участках земляной дамбы на Жабае, что привело к подтоплению Атбасара."),
    "Evacuation and protection measures underway; more than 400 people and 100 equipment units were engaged.": (
        "Эвакуация және қорғау шаралары жүргізілуде; 400-ден астам адам және 100 техника бірлігі тартылды.",
        "Ведутся эвакуация и защитные мероприятия; задействовано более 400 человек и 100 единиц техники."),
    "Regional report: Zhabai level decreased from 5.5 m to 5.0 m; damaged roads and flooded yards were being restored/pumped.": (
        "Өңірлік есеп: Жабай деңгейі 5,5 м-ден 5,0 м-ге төмендеді; бүлінген жолдар қалпына келтіріліп, су басқан аулалардан су сорылуда.",
        "Региональная сводка: уровень Жабая снизился с 5,5 до 5,0 м; повреждённые дороги восстанавливаются, из подтопленных дворов откачивается вода."),
    "Zhabai level reported at 3.80 m; regional authorities described the critical period as passed and recovery underway.": (
        "Жабай деңгейі 3,80 м деп хабарланды; өңірлік билік сыни кезең өтті және қалпына келтіру жүріп жатыр деп мәлімдеді.",
        "Уровень Жабая — 3,80 м; региональные власти сообщили, что критический период пройден и идёт восстановление."),
    "Flood threat in Akmola reported as passed; Zhabai level reported at 2.8 m.": (
        "Ақмола облысында су тасқыны қаупі өтті деп хабарланды; Жабай деңгейі 2,8 м.",
        "Угроза паводка в Акмолинской области миновала; уровень Жабая — 2,8 м."),
    ("Retrospective statement: during the flood the Zhabai level rose to 6.20 m. Exact peak timestamp is not stated, "
     "so this must not be inserted as a timestamped gauge observation."): (
        "Ретроспективалық мәлімдеме: су тасқыны кезінде Жабай деңгейі 6,20 м-ге дейін көтерілді. Шыңның нақты уақыты "
        "көрсетілмеген, сондықтан бұл уақыт белгісі бар бекет бақылауы ретінде енгізілмейді.",
        "Ретроспективное заявление: во время паводка уровень Жабая поднимался до 6,20 м. Точное время пика не указано, "
        "поэтому значение не вносится как наблюдение поста с отметкой времени."),
    "Overflow/temporary access restriction reported near the bridge.": (
        "Көпір маңында су асуы / уақытша қозғалыс шектеуі хабарланды.",
        "У моста сообщалось о переливе / временном ограничении движения."),
    ("16 private houses, 29 private yards, 12 apartment courtyards and the first floor of Ertostik kindergarten were "
     "reported affected."): (
        "16 жеке үй, 29 жеке аула, 12 көппәтерлі үй ауласы және «Ертөстік» балабақшасының бірінші қабаты зардап шекті деп хабарланды.",
        "Сообщается о подтоплении 16 частных домов, 29 частных дворов, 12 дворов многоквартирных домов и первого этажа детского сада «Ертостик»."),
    "113 people evacuated, including 30 children.": (
        "113 адам эвакуацияланды, оның ішінде 30 бала.", "Эвакуированы 113 человек, в том числе 30 детей."),
    "Local emergency status reported.": (
        "Жергілікті төтенше жағдай режимі жарияланды.", "Объявлен местный режим чрезвычайной ситуации."),
    ("Protective berm/bypass works and blockage clearing near the bridge were reported; river level decreased by about 70 cm."): (
        "Көпір маңында қорғаныс үйіндісі/айналма арна жұмыстары және кептелісті тазарту жүргізілді; өзен деңгейі шамамен 70 см-ге төмендеді.",
        "У моста проведены работы по защитному валу/обводу и расчистке завала; уровень реки снизился примерно на 70 см."),
    # bottleneck candidate notes (build.py)
    "Candidate low road section: inundated in the BASE member (terrain-conditioned model).": (
        "Ойпаң жол учаскесі (үміткер): BASE мүшесінде су басады (жер бедеріне негізделген модель).",
        "Кандидат — низкий участок дороги: затапливается в члене BASE (модель с учётом рельефа)."),
    "Candidate operational bottleneck (OSM bridge); no surveyed hydraulic capacity.": (
        "Жедел тар орын (үміткер, OSM көпірі); гидравликалық өткізу қабілеті өлшенбеген.",
        "Кандидат — оперативное узкое место (мост OSM); гидравлическая пропускная способность не обследована."),
    "Candidate channel crossing: unclassified road crosses mapped OSM river without a bridge tag. No surveyed dimensions.": (
        "Арна қиылысы (үміткер): жіктелмеген жол OSM-дегі өзенді көпір белгісінсіз қиып өтеді. Өлшемдері өлшенбеген.",
        "Кандидат — пересечение русла: дорога без класса пересекает реку OSM без отметки моста. Размеры не обследованы."),
    "Candidate culvert: tertiary road crosses mapped OSM stream without a bridge tag. No surveyed dimensions.": (
        "Су өткізгіш (үміткер): үшінші санатты жол OSM-дегі бұлақты көпір белгісінсіз қиып өтеді. Өлшемдері өлшенбеген.",
        "Кандидат — водопропуск: дорога третьего класса пересекает ручей OSM без отметки моста. Размеры не обследованы."),
    ("Candidate low road section: lowest-lying major road segments relative to the Kylshakty (real DEM) — inundated in "
     "the BASE exercise member."): (
        "Ойпаң жол учаскесі (үміткер): Қылшақтыға қатысты ең төмен орналасқан негізгі жол учаскелері (нақты DEM) — "
        "BASE жаттығу мүшесінде су басады.",
        "Кандидат — низкий участок дороги: самые низкие участки основных дорог относительно Кылшакты (реальная ЦМР) — "
        "затапливаются в учебном члене BASE."),
    "Candidate operational bottleneck: OSM bridge over the Kylshakty. No surveyed hydraulic capacity.": (
        "Жедел тар орын (үміткер): Қылшақты арқылы өтетін OSM көпірі. Гидравликалық өткізу қабілеті өлшенбеген.",
        "Кандидат — оперативное узкое место: мост OSM через Кылшакты. Гидравлическая пропускная способность не обследована."),
    "Candidate operational bottleneck: OSM bridge. No surveyed hydraulic capacity.": (
        "Жедел тар орын (үміткер): OSM көпірі. Гидравликалық өткізу қабілеті өлшенбеген.",
        "Кандидат — оперативное узкое место: мост OSM. Гидравлическая пропускная способность не обследована."),
    # report notes
    "All DEMO fixtures are synthetic.": (
        "Барлық DEMO деректері синтетикалық.", "Все DEMO-данные синтетические."),
    "Economic values are ranges based on stated assumptions.": (
        "Экономикалық мәндер — көрсетілген болжамдарға негізделген аралықтар.",
        "Экономические значения — диапазоны на основе указанных допущений."),
    "Flood surfaces come from precomputed scenario members (no hydrodynamic simulation in ARGUS).": (
        "Су басу беттері алдын ала есептелген сценарий мүшелерінен алынады (ARGUS гидродинамикалық есептеу жүргізбейді).",
        "Поверхности затопления берутся из заранее рассчитанных членов сценария (ARGUS не выполняет гидродинамическое моделирование)."),
    # exercise inject (Atbasar plans.json)
    ("EXERCISE INJECT: duty forecaster warns the Zhabai may exceed 6.0 m (2024 recorded maximum 6.20 m) — "
     "HIGH stress member selected"): (
        "ЖАТТЫҒУ ИНЪЕКЦИЯСЫ: кезекші синоптик Жабай деңгейі 6,0 м-ден асуы мүмкін екенін ескертеді (2024 жылғы "
        "тіркелген ең жоғары деңгей 6,20 м) — HIGH стресс мүшесі таңдалды",
        "ВВОДНАЯ УЧЕНИЙ: дежурный прогнозист предупреждает, что уровень Жабая может превысить 6,0 м (зафиксированный "
        "максимум 2024 г. — 6,20 м) — выбран стресс-член HIGH"),
}


def tri(en: str | None) -> dict | None:
    """{kk, ru, en} for an English source sentence (English fallback when no rendering exists)."""
    if en is None:
        return None
    kk, ru = TR.get(en, (en, en))
    return {"kk": kk, "ru": ru, "en": en}
