<template>
  <section class="asset-panel" :data-testid="'asset-editor-' + kind">
    <header class="asset-header">
      <div><h2>{{ kind === 'scenarios' ? '场景资产' : '固定版本套件' }} <span class="count-badge">{{ assets.length }}</span></h2><p>编辑草稿 → 预检发布 → 选择版本运行</p></div>
      <div class="toolbar"><button type="button" @click="load" :disabled="busy">{{ busy ? '处理中…' : '刷新' }}</button><button class="action-button" type="button" @click="createDraft" :disabled="busy"><span aria-hidden="true">＋</span> 新增</button></div>
    </header>
    <p v-if="error" class="state-banner state-banner--error" role="alert">{{ error }}</p>
    <p v-if="message" class="state-banner state-banner--info" role="status">{{ message }}</p>
    <div class="asset-grid">
      <aside class="asset-library" aria-label="资产列表">
        <label class="asset-search"><span>搜索资产</span><input v-model="search" type="search" placeholder="名称、标签或 ID" /></label>
        <p class="asset-library__count">{{ search ? `找到 ${filteredAssets.length} 个结果` : `全部资产 · ${assets.length}` }}</p>
        <ul class="asset-list" :aria-busy="busy">
          <li v-for="item in filteredAssets" :key="item.id">
            <button type="button" class="asset-list__item" :class="{ 'asset-list__item--selected': selected?.id === item.id }" :aria-pressed="selected?.id === item.id" @click="chooseAsset(item)" :disabled="busy">
              <span class="asset-list__name">{{ item.draft.name }}</span><span class="asset-list__meta"><span class="asset-priority">{{ item.draft.priority }}</span><span>草稿 r{{ item.revision }}</span></span>
              <span v-if="item.draft.tags?.length" class="asset-list__tags">{{ item.draft.tags.join(' · ') }}</span>
            </button>
          </li>
        </ul>
        <div v-if="!filteredAssets.length" class="asset-empty"><strong>{{ busy ? '正在加载…' : search ? '没有匹配的资产' : '还没有资产' }}</strong><p>{{ search ? '试试其他关键词，或清空搜索。' : '点击“新增”创建第一份草稿。' }}</p><button v-if="search" type="button" @click="search = ''">清空搜索</button></div>
      </aside>
      <form class="asset-form" @submit.prevent="save" @invalid.capture="revealInvalid">
        <div class="editor-heading">
          <div>
            <span class="editor-eyebrow">{{ selected ? '编辑草稿' : '新建草稿' }}</span>
            <h3>{{ selected ? name || '未命名资产' : kind === 'scenarios' ? '创建业务场景' : '创建测试套件' }}</h3>
          </div>
          <div class="toolbar">
            <span class="draft-state">{{ dirty ? '未保存' : selected ? '已保存' : '待创建' }}</span>
            <button v-if="kind === 'scenarios'" type="button" :disabled="busy" @click="openDebug()">调试当前整场景</button>
            <button class="action-button" :disabled="busy || !dirty">保存</button>
          </div>
        </div>
        <details class="editor-details scenario-settings" :open="settingsOpen" @toggle="settingsOpen = ($event.target as HTMLDetailsElement).open">
          <summary>{{ kind === 'scenarios' ? '场景设置' : '套件设置' }}</summary>
          <div class="settings-content">
        <div class="form-section-title">基本信息</div>
        <div class="editor-fields">

        <label>名称 <input v-model="name" required /></label>
        <label><span class="field-caption"><span>优先级</span><HelpHint topic="priority" /></span><select v-model="priority" aria-label="优先级"><option>P0</option><option>P1</option><option>P2</option></select></label>
        <label><span class="field-caption"><span>标签（逗号分隔）</span><HelpHint topic="tags" /></span><input v-model="tags" placeholder="smoke,core" aria-label="标签（逗号分隔）" /></label>
        </div>
        <template v-if="kind === 'scenarios'">
          <div class="form-section-title">执行上下文 <small>配置目标系统与测试身份</small></div>
          <div class="editor-fields">
          <label><span class="field-caption"><span>目标系统</span><HelpHint topic="target" /></span><select v-model="targetRef" required aria-label="目标系统">
            <option v-for="target in targets" :key="target.id" :value="target.id">{{ target.name }} · {{ target.id }}</option>
          </select></label>
          <label><span class="field-caption"><span>身份（可选）</span><HelpHint topic="identity" /></span><select v-model="identityRef" aria-label="身份（可选）"><option value="">无</option><option v-for="item in availableIdentities" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label><span class="field-caption"><span>租户 / 项目绑定</span><HelpHint topic="binding" /></span><select v-model="bindingRef" aria-label="租户 / 项目绑定"><option value="">无</option><option v-for="item in availableBindings" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label>模块 <input v-model="moduleName" /></label>
          </div>
          <details class="editor-details"><summary aria-label="场景参数 参数约束与默认值">场景参数 <span>参数约束与默认值</span><HelpHint topic="schema" /></summary><div class="editor-fields">
          <label><span class="field-caption"><span>参数 schema（名称 → type/required）</span><HelpHint topic="schema" /></span><textarea v-model="parametersSchema" rows="3" aria-label="参数 schema（名称 → type/required）" /></label>
          <label><span class="field-caption"><span>默认公开参数</span><HelpHint topic="parameters" /></span><textarea v-model="parameters" rows="3" aria-label="默认公开参数" /></label>
          </div></details>
        </template>
          </div>
        </details>
        <template v-if="kind === 'scenarios'">
          <div class="form-section-title">请求步骤 <small>{{ steps.length }} 个步骤 · 按依赖顺序执行</small></div>
          <p v-if="!steps.length" class="step-empty">暂无请求步骤。添加 HTTP 步骤，配置请求和预期结果。</p>
          <nav class="step-navigation" aria-label="步骤导航"><button v-for="(step, index) in steps" :key="index" type="button" @click="focusStep(index)">{{ index + 1 }} · {{ step.name || step.step_id }}</button></nav>
          <ScenarioDebugPanel v-if="kind === 'scenarios' && debugOpen" :key="(selected?.id || 'new') + ':' + debugStep" :get-draft="validatedDraft" :asset-id="selected?.id" :revision="selected?.revision" :step-id="debugStep" :environments="environments" />
          <fieldset class="step-card" v-for="(step, index) in steps" :id="'scenario-step-' + index" :key="stepKey(step)" :aria-label="'步骤 ' + (index + 1)">
            <legend>步骤 {{ index + 1 }} · {{ step.name }}</legend>
            <div class="toolbar"><button type="button" @click="toggleStep(step.step_id)" :aria-expanded="!collapsed.includes(step.step_id)">{{ collapsed.includes(step.step_id) ? '展开' : '折叠' }}</button><button type="button" @click="copyStep(index)">复制步骤</button><button type="button" :disabled="index === 0" @click="moveStep(index, -1)">上移</button><button type="button" :disabled="index === steps.length - 1" @click="moveStep(index, 1)">下移</button><button type="button" :disabled="Boolean(step.database_check)" @click="openDebug(step.step_id)">仅调试此步骤</button></div>
            <div v-show="!collapsed.includes(step.step_id)" class="step-content">
            <div v-if="step.database_check" class="state-banner state-banner--info">
              <span class="field-caption">只读数据库核验<HelpHint topic="receptionPack" /></span>
              <p>数据源：{{ step.database_check.datasource_ref }} · 规则：{{ step.database_check.contract_ref }}</p>
              <p>本步骤同时核对数据库期望；缺数据、权限变化或连接失败会明确报错。调试时请使用“调试当前整场景”，以便先核对身份和项目。</p>
              <p>回归包按测试项目内的现有数据选取筛选样本，实际条件会记录在运行请求中。</p>
            </div>
            <div class="editor-fields">
            <label><span class="field-caption"><span>稳定 ID</span><HelpHint topic="stepId" /></span><input v-model="step.step_id" required aria-label="稳定 ID" /></label>
            <label>步骤名称 <input v-model="step.name" required /></label>
            <label><span class="field-caption"><span>步骤类型</span><HelpHint topic="stepType" /></span><select v-model="step.type" aria-label="步骤类型"><option value="http">HTTP</option><option value="wait_until">等待异步终态</option></select></label>
            <label><span class="field-caption"><span>阶段</span><HelpHint topic="phase" /></span><select v-model="step.phase" aria-label="阶段"><option>setup</option><option>action</option><option>verify</option><option>cleanup</option></select></label>

            <label><span class="field-caption"><span>方法</span><HelpHint topic="method" /></span><select v-model="step.method" aria-label="方法"><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></label>
            <label><span class="field-caption"><span>URL</span><HelpHint topic="url" /></span><input v-model="step.url" placeholder="{{host}}/api/v1/..." required aria-label="URL" /></label>
            <label><span class="field-caption"><span>业务用途</span><HelpHint topic="operation" /></span><select v-model="step.operation_kind" aria-label="业务用途"><option value="query">查询</option><option value="write">写入</option></select></label>
            </div>
            <label><input type="checkbox" v-model="step.contract_confirmed" aria-label="请求契约已确认，可进入真实运行预检" /><span class="field-caption">请求契约已确认，可进入真实运行预检<HelpHint topic="contract" /></span></label>
            <details class="editor-details"><summary aria-label="请求选项 请求头、参数、请求体与重放策略">请求选项 <span>请求头、参数、请求体与重放策略</span><HelpHint topic="headers" /></summary><div class="advanced-fields">
            <label><span class="field-caption"><span>依赖（逗号分隔的前置步骤 ID）</span><HelpHint topic="dependencies" /></span><input v-model="step.dependenciesText" aria-label="依赖（逗号分隔的前置步骤 ID）" /></label>
            <label><input type="checkbox" v-model="step.safe_to_replay" aria-label="此查询已确认允许401后重放一次" /><span class="field-caption">此查询已确认允许401后重放一次<HelpHint topic="replay" /></span></label>
            <fieldset aria-label="请求头"><legend>请求头<HelpHint topic="headers" /></legend><div v-for="(row, i) in step.headerRows" :key="i" class="request-row"><input v-model="row.key" aria-label="请求头名称" /><input v-model="row.value" aria-label="请求头值" /><button type="button" @click="step.headerRows.splice(i, 1)">移除</button></div><button type="button" @click="step.headerRows.push({key: '', value: ''})">添加请求头</button></fieldset>
            <fieldset aria-label="查询参数"><legend>查询参数<HelpHint topic="query" /></legend><div v-for="(row, i) in step.queryRows" :key="i" class="request-row"><input v-model="row.key" aria-label="查询参数名称" /><input v-model="row.value" aria-label="查询参数值" /><button type="button" @click="step.queryRows.splice(i, 1)">移除</button></div><button type="button" @click="step.queryRows.push({key: '', value: ''})">添加查询参数</button></fieldset>
            <label><span class="field-caption"><span>请求体类型</span><HelpHint topic="bodyType" /></span><select v-model="step.bodyType" aria-label="请求体类型"><option value="none">无</option><option value="json">JSON</option><option value="form">表单</option><option value="raw">原始文本</option></select></label>
            <label><span class="field-caption"><span>请求体（JSON/表单填写 JSON，原始文本直接填写）</span><HelpHint topic="body" /></span><textarea v-model="step.bodyText" rows="3" aria-label="请求体（JSON/表单填写 JSON，原始文本直接填写）" /></label>
            </div></details>
            <AssertionEditor v-model="step.assertionsText" />
            <fieldset v-if="step.type === 'wait_until'">
              <legend>有限状态轮询</legend>
              <label><input v-model="step.waitConfirmed" type="checkbox" aria-label="状态/查询契约已确认" /><span class="field-caption">状态/查询契约已确认<HelpHint topic="contract" /></span></label>
              <label><span class="field-caption"><span>状态字段</span><HelpHint topic="stateSelector" /></span><input v-model="step.stateSelector" aria-label="状态字段" /></label>
              <label><span class="field-caption"><span>状态映射 JSON</span><HelpHint topic="stateMap" /></span><textarea v-model="step.stateMapText" rows="4" aria-label="状态映射 JSON" /></label>
              <label><span class="field-caption"><span>间隔（秒）</span><HelpHint topic="pollInterval" /></span><input v-model.number="step.pollInterval" type="number" min="0" step="any" aria-label="间隔（秒）" /></label>
              <label><span class="field-caption"><span>总等待预算（秒）</span><HelpHint topic="pollDeadline" /></span><input v-model.number="step.pollDeadline" type="number" min="0.001" step="any" aria-label="总等待预算（秒）" /></label>
              <label><span class="field-caption"><span>最大次数</span><HelpHint topic="pollAttempts" /></span><input v-model.number="step.pollAttempts" type="number" min="1" aria-label="最大次数" /></label>
              <label><span class="field-caption"><span>安全查询网络重试（0—3）</span><HelpHint topic="networkRetries" /></span><input v-model.number="step.networkRetries" type="number" min="0" max="3" aria-label="安全查询网络重试（0—3）" /></label>
              <details><summary aria-label="高级等待策略 JSON（退避/谓词/轨迹上限）">高级等待策略 JSON（退避/谓词/轨迹上限）<HelpHint topic="waitPolicy" /></summary><textarea v-model="step.waitPolicyText" rows="6" /></details>
            </fieldset>
            <ExtractorEditor v-model="step.extractorsText" :step-id="step.step_id" />
            <button class="action-button action-button--danger step-delete" type="button" @click="steps.splice(index, 1)">删除步骤</button>
            </div>
          </fieldset>
          <button type="button" @click="addStep">添加 HTTP 步骤</button>
        </template>
        <template v-else>
          <div class="form-section-title">场景编排 <small>引用固定发布版本</small></div>
          <label><span class="field-caption"><span>总预算（秒）</span><HelpHint topic="budget" /></span><input v-model.number="budget" type="number" min="1" max="86400" aria-label="总预算（秒）" /></label>
          <fieldset v-for="(ref, index) in scenarioRefs" :key="index">
            <legend>场景引用 {{ index + 1 }}</legend>
            <label><span class="field-caption"><span>场景</span><HelpHint topic="scenarioRef" /></span><select v-model="ref.scenario_id" required aria-label="场景" @change="changeScenarioReference(ref)"><option value="" disabled>选择场景</option><option v-for="item in scenarioOptions" :key="item.id" :value="item.id">{{ item.draft.name }}</option></select></label>
            <label><span class="field-caption"><span>固定发布版本</span><HelpHint topic="version" /></span><select v-model.number="ref.version" required aria-label="固定发布版本" :disabled="!ref.scenario_id || referenceLoading[ref.scenario_id]">
              <option :value="0" disabled>选择已发布版本</option>
              <option v-if="ref.version && !referenceVersions[ref.scenario_id]?.some(item => item.version === ref.version)" :value="ref.version" disabled>v{{ ref.version }} · 待核验 / 未找到</option>
              <option v-for="version in referenceVersions[ref.scenario_id] || []" :key="version.version" :value="version.version">v{{ version.version }} · {{ version.change_note }}</option>
            </select></label>
            <p v-if="referenceLoading[ref.scenario_id]" role="status">正在核验已发布版本，保留当前引用。</p>
            <p v-else-if="referenceErrors[ref.scenario_id]" role="alert">{{ referenceErrors[ref.scenario_id] }}</p>
            <p v-else-if="ref.version && referenceVersions[ref.scenario_id] && !referenceVersions[ref.scenario_id]?.some(item => item.version === ref.version)" role="alert">当前固定版本未找到，请重新选择已发布版本。</p>
            <button v-if="ref.scenario_id" type="button" :disabled="referenceLoading[ref.scenario_id]" @click="loadReferenceVersions(ref.scenario_id, true)">刷新发布版本</button>
            <button type="button" @click="scenarioRefs.splice(index, 1)">移除</button>
          </fieldset>
          <button type="button" @click="scenarioRefs.push({ scenario_id: '', version: 1 })">添加固定场景版本</button>
        </template>
        <details v-if="kind === 'scenarios'"><summary aria-label="迁移与扩展元数据">迁移与扩展元数据<HelpHint topic="migration" /></summary>
          <p>迁移缺口解决后再更新 migration_blockers；不能删除仍然未知的业务契约来绕过预检。</p>
          <textarea v-model="draftExtras" rows="8" aria-label="迁移与扩展元数据" />
        </details>
        <p v-if="dirty" class="state-banner state-banner--info">有未保存修改；请先保存，再预检或发布。</p>
        <p class="asset-id">{{ selected ? `ID: ${selected.id} · r${selected.revision}` : '保存后自动生成资产 ID' }}</p>
        <div class="editor-save-bar"><button class="action-button" :disabled="busy">{{ busy ? '处理中…' : '保存草稿' }}</button><span class="action-help" v-if="selected"><button type="button" @click="preflight" :disabled="busy || dirty">发布预检</button><HelpHint topic="preflight" /></span><button type="button" v-if="selected" @click="copyAsset" :disabled="busy">复制</button><span class="action-help" v-if="selected"><button class="action-button action-button--danger" type="button" @click="archive" :disabled="busy">归档草稿</button><HelpHint topic="archive" /></span></div>
        <section v-if="selected" class="publish-section"><div class="form-section-title">发布版本 <small>发布后内容不可变</small></div><label><span class="field-caption"><span>发布说明</span><HelpHint topic="publish" /></span><input v-model="changeNote" placeholder="说明本次调整，便于追溯" aria-label="发布说明" /></label><span class="action-help"><button type="button" @click="publish" :disabled="busy || dirty || !changeNote">发布不可变版本</button><HelpHint topic="publish" /></span></section>
      </form>
    </div>
    <pre v-if="checkResult">{{ checkResult }}</pre>
    <section v-if="selected" class="version-section">
      <div class="section-heading"><div><h3>已发布版本</h3><p>选择固定版本，预览计划后提交运行。</p></div><span class="count-badge">{{ versions.length }} 个版本</span></div>
      <p v-if="!versions.length" class="empty-copy">尚未发布版本。保存草稿并完成预检后，填写发布说明进行发布。</p>
      <div class="editor-fields">
      <label><span class="field-caption"><span>选择版本</span><HelpHint topic="version" /></span><select v-model.number="chosenVersion" aria-label="选择版本"><option v-for="version in versions" :key="version.version" :value="version.version">v{{ version.version }} · {{ version.change_note }}</option></select></label>
      <label><span class="field-caption"><span>运行环境</span><HelpHint topic="runEnvironment" /></span><select v-model="runEnvironment" aria-label="运行环境"><option value="">按已发布目标自动确定</option><option v-for="env in environments" :key="env.id" :value="env.id">{{ env.name }}</option></select></label>
      <label><span class="field-caption"><span>被测构建</span><HelpHint topic="build" /></span><input v-model="build" placeholder="填写实际版本；未知构建不能用于发布" aria-label="被测构建" /></label>
      <label><span class="field-caption"><span>本次公开参数 JSON</span><HelpHint topic="parameters" /></span><textarea v-model="runParameters" rows="3" aria-label="本次公开参数 JSON" /></label>
      </div><div class="toolbar"><span class="action-help"><button type="button" :disabled="busy || !chosenVersion" @click="plan">计划预览</button><HelpHint topic="plan" /></span></div>
      <label><input v-model="liveConfirmed" type="checkbox" aria-label="已核对计划与测试数据/写入范围" /><span class="field-caption">已核对计划与测试数据/写入范围<HelpHint topic="liveConfirmation" /></span></label>
      <div class="toolbar"><span class="action-help"><button class="action-button" type="button" :disabled="busy || !chosenVersion || !liveConfirmed" @click="run">提交运行</button><HelpHint topic="run" /></span>
      <span class="action-help"><button type="button" :disabled="busy || !chosenVersion" @click="exportAsset">查看脱敏导出</button><HelpHint topic="export" /></span></div>
    </section>
    <div v-if="kind === 'scenarios'" class="asset-imports"><details><summary aria-label="接入言迹测试环境查询包">接入言迹测试环境查询包<HelpHint topic="yanjiPack" /></summary>
      <p>选择目标、身份和项目绑定后，填写测试用户 ID。仅创建查询草稿，不发送请求。</p>
      <span class="action-help"><button type="button" :disabled="busy" @click="showYanjiContracts">查看四组契约与所缺资源</button><HelpHint topic="yanjiPack" /></span>
      <label><span class="field-caption"><span>预期测试用户 ID</span><HelpHint topic="expectedUser" /></span><input v-model="expectedUserId" aria-label="预期测试用户 ID" /></label>
      <span class="action-help"><button type="button" :disabled="busy || !targetRef || !identityRef || !bindingRef || !expectedUserId" @click="importYanji">创建查询草稿</button><HelpHint topic="yanjiPack" /></span>
      <details class="reception-import" @toggle="onReceptionToggle">
        <summary aria-label="接诊记录筛选回归">接诊记录筛选回归<HelpHint topic="receptionPack" /></summary>
        <p>核对筛选后的接诊单、总数和分页。沿用上方目标、身份、项目绑定及预期用户 ID，只读取业务数据。</p>
        <label><span class="field-caption"><span>言迹业务数据源</span><HelpHint topic="businessDatasource" /></span>
          <select v-model="datasourceRef" aria-label="言迹业务数据源" :disabled="busy || datasourceLoading">
            <option value="">选择已配置的数据源</option>
            <option v-for="source in datasources" :key="source.id" :value="source.id">{{ source.id }} · {{ source.schema }} · {{ source.configuration === 'passed' ? '配置就绪' : '配置待修复' }}</option>
          </select>
        </label>
        <p v-if="datasourceLoading" role="status">正在读取业务数据源配置…</p>
        <p v-if="datasourceError" class="state-banner state-banner--error" role="alert">{{ datasourceError }}</p>
        <p v-else-if="datasourcesLoaded && !datasources.length">尚未配置业务数据源。请在服务端配置言迹测试库及秘密引用，再刷新列表。</p>
        <div class="toolbar">
          <button type="button" :disabled="busy || datasourceLoading" @click="loadDatasources">刷新数据源</button>
          <span class="action-help"><button type="button" :disabled="busy || !receptionReady" @click="preflightDatasource(false)">检查数据源配置</button><HelpHint topic="businessDatasource" /></span>
          <span class="action-help"><button type="button" :disabled="busy || !receptionReady" @click="preflightDatasource(true)">验证数据库连接与权限</button><HelpHint topic="businessDatasourceProbe" /></span>
        </div>
        <div v-if="datasourcePreflight" class="datasource-result" role="status">
          <p>配置：{{ datasourceStatus(datasourcePreflight.configuration) }} · 连接：{{ datasourceStatus(datasourcePreflight.connection) }} · 权限：{{ datasourceStatus(datasourcePreflight.permission) }}</p>
          <p v-if="datasourcePreflight.errors?.length">{{ datasourcePreflight.errors.join('；') }}</p>
        </div>
        <span class="action-help"><button type="button" :disabled="busy || !receptionReady" @click="importReceptions">创建接诊筛选回归草稿</button><HelpHint topic="receptionPack" /></span>
        <p>创建后选择场景进行预检、发布，再编排固定版本套件。创建草稿不执行接口，也不会启用定时任务。</p>
      </details>
    </details><details><summary aria-label="迁移已有资产（只创建草稿，不发送请求）">迁移已有资产（只创建草稿，不发送请求）<HelpHint topic="import" /></summary>
      <label v-if="importKind === 'legacy'"><span class="field-caption"><span>旧 YAML 内容</span><HelpHint topic="import" /></span><textarea v-model="importSource" rows="8" placeholder="粘贴 YAML；导入时会移除旧秘密值" aria-label="旧 YAML 内容" /></label>
      <label><span class="field-caption"><span>导入类型</span><HelpHint topic="import" /></span><select v-model="importKind" aria-label="导入类型"><option value="legacy">旧 YAML</option><option value="standard">标准发布 JSON</option></select></label>
      <label v-if="importKind === 'standard'"><span class="field-caption"><span>发布 JSON</span><HelpHint topic="import" /></span><textarea v-model="importText" rows="10" aria-label="发布 JSON" /></label>
      <span class="action-help"><button type="button" :disabled="busy" @click="importAsset">导入并显示迁移报告</button><HelpHint topic="import" /></span>
    </details></div>
  </section>
</template>

<script setup lang="ts">
import HelpHint from '@/components/common/HelpHint.vue';
import { computed, onMounted, onBeforeUnmount, nextTick, ref, watch } from 'vue';
import { useRouter, useRoute, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router';
import ExtractorEditor from '@/components/ExtractorEditor.vue';
import ScenarioDebugPanel from '@/components/ScenarioDebugPanel.vue';
import AssertionEditor from '@/components/AssertionEditor.vue';
import { apiClient } from '@/api/client';
import { resolveApiErrorMessage } from '@/utils/apiErrors';

interface Step {
  step_id: string; name: string; type: string; phase: string;
  depends_on: string[]; operation_kind: string; contract_confirmed: boolean; safe_to_replay: boolean;
  request: { method: string; url: string; body: unknown; [key: string]: unknown };
  assertions: unknown[]; extractors: unknown[]; wait_policy?: Record<string, unknown> | null; [key: string]: unknown;
}
interface Pair { key: string; value: string; original?: unknown }
interface Profile { id: string; name: string; target_ids?: string[]; target_id?: string; identity_id?: string }
interface EditorStep extends Omit<Step, 'request'> {
  step_id: string; name: string; type: string; phase: string;
  operation_kind: string; contract_confirmed: boolean; safe_to_replay: boolean;
  request?: Step['request']; method: string; url: string; dependenciesText: string;
  headerRows: Pair[]; queryRows: Pair[]; bodyType: string; bodyText: string; assertionsText: string; extractorsText: string;
  waitConfirmed: boolean; stateSelector: string; stateMapText: string; pollInterval: number;
  pollDeadline: number; pollAttempts: number; networkRetries: number; waitPolicyText: string;
  database_check?: { datasource_ref: string; contract_ref: string } | null;
}
interface Data {
  name: string; priority: string; tags?: string[]; target_ref?: string;
  identity_ref?: string | null; identity_binding_ref?: string | null; module?: string;
  parameters_schema?: Record<string, unknown>; parameters?: Record<string, unknown>;
  steps?: Step[]; scenarios?: {scenario_id: string; version: number}[]; timeout_seconds?: number;
  [key: string]: unknown;
}
interface Asset { id: string; revision: number; draft: Data }
interface Version { version: number; change_note: string }
interface BusinessDatasource { id: string; schema: string; configuration: string }
interface DatasourcePreflight { configuration: string; connection: string; permission: string; errors: string[] }
const props = defineProps<{ kind: 'scenarios' | 'suites' }>();
const emit = defineEmits<{ (event: 'saved', asset: { id: string }): void; (event: 'selected', assetId: string): void }>();
const router = useRouter();
const route = useRoute();
const formalNavigation = ref(false);
const settingsOpen = ref(true);
function revealInvalid(event: Event) {
  const control = event.target as HTMLElement;
  // Native validation runs before submit, so expand synchronously before the browser focuses.
  for (let parent = control.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === 'DETAILS') (parent as HTMLDetailsElement).open = true;
    if (parent.classList.contains('scenario-settings')) settingsOpen.value = true;
    if (parent.classList.contains('step-content')) parent.style.display = '';
  }
  const card = control.closest('.step-card');
  if (card) {
    const step = steps.value[Number(card.id.replace('scenario-step-', ''))];
    if (step) collapsed.value = collapsed.value.filter(id => id !== step.step_id);
  }
}
const collapsed = ref<string[]>([]);
const stepKeys = new WeakMap<object, number>();
let stepKeySequence = 0;
function stepKey(step: EditorStep) { if (!stepKeys.has(step)) stepKeys.set(step, ++stepKeySequence); return stepKeys.get(step); }
const debugStep = ref('');
const debugOpen = ref(false);
async function openDebug(stepId = '') { debugStep.value = stepId; debugOpen.value = true; await nextTick(); const panel = document.querySelector<HTMLElement>('[aria-label="当前草稿调试"]'); panel?.scrollIntoView({ block: 'start' }); panel?.focus({ preventScroll: true }); }
function toggleStep(id: string) { collapsed.value = collapsed.value.includes(id) ? collapsed.value.filter(item => item !== id) : [...collapsed.value, id]; }
async function focusStep(index: number, field = '') {
  const step = steps.value[index]; if (!step) return;
  collapsed.value = collapsed.value.filter(id => id !== step.step_id);
  await nextTick();
  const card = document.getElementById(`scenario-step-${index}`);
  card?.querySelectorAll('details').forEach(item => item.open = true);
  card?.scrollIntoView({ block: 'nearest' });
  const captions: Record<string, string> = { '断言 JSON': '完整结构化断言 JSON', '变量提取 JSON': '提取 JSON', '请求体': '请求体（', '依赖': '依赖（' };
  const label = field ? [...(card?.querySelectorAll('label') || [])].find(item => item.textContent?.includes(captions[field] || field)) : undefined;
  const control = label?.querySelector('input,textarea,select') || card?.querySelector('input,textarea,select');
  (control as HTMLElement | null)?.focus();
}
function moveStep(index: number, offset: number) {
  const destination = index + offset;
  if (destination < 0 || destination >= steps.value.length) return;
  const [step] = steps.value.splice(index, 1); if (step) steps.value.splice(destination, 0, step);
}
function uniqueStepId() { let index = 1; while (steps.value.some(step => step.step_id === `step_${index}`)) index++; return `step_${index}`; }
function copyStep(index: number) {
  const original = steps.value[index]; if (!original) return;
  const copy = JSON.parse(JSON.stringify(original)) as EditorStep;
  const id = uniqueStepId(); copy.extractorsText = copy.extractorsText.replaceAll(`outputs.${copy.step_id}.`, `outputs.${id}.`);
  copy.step_id = id; copy.name += ' 副本'; steps.value.splice(index + 1, 0, copy);
}
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value) { event.preventDefault(); event.returnValue = ''; } }
onBeforeRouteLeave(() => formalNavigation.value || (!busy.value && canLeaveDraft()));
onBeforeRouteUpdate(to => to.query.assetId === route.query.assetId || canLeaveDraft());
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload));

const assets = ref<Asset[]>([]), selected = ref<Asset | null>(null), targets = ref<{id: string; name: string}[]>([]);
const busy = ref(false), error = ref(''), message = ref(''), checkResult = ref('');
const name = ref(''), priority = ref('P1'), tags = ref('core'), moduleName = ref('未分类');
const targetRef = ref(''), identityRef = ref(''), bindingRef = ref('');
const draftExtras = ref('{}');
const parametersSchema = ref('{}'), parameters = ref('{}'), steps = ref<EditorStep[]>([]);
const scenarioRefs = ref<{scenario_id: string; version: number}[]>([]), budget = ref(300);
const referenceVersions = ref<Record<string, Version[]>>({});
const referenceLoading = ref<Record<string, boolean>>({});
const referenceErrors = ref<Record<string, string>>({});
const referenceRequests = new Map<string, Promise<Version[]>>();
async function loadReferenceVersions(id: string, force = false): Promise<Version[]> {
  if (!id) return [];
  const pending = referenceRequests.get(id); if (pending) return pending;
  if (!force && referenceVersions.value[id]) return referenceVersions.value[id]!;
  referenceLoading.value[id] = true; referenceErrors.value[id] = '';
  const request = apiClient.get<Version[]>(`/scenarios/${encodeURIComponent(id)}/versions`)
    .then(data => { referenceVersions.value[id] = data; return data; })
    .catch(cause => { referenceErrors.value[id] = resolveApiErrorMessage(cause, '发布版本核验失败，请重试'); throw cause; })
    .finally(() => { referenceLoading.value[id] = false; referenceRequests.delete(id); });
  referenceRequests.set(id, request);
  return request;
}
async function changeScenarioReference(reference: {scenario_id: string; version: number}) {
  const id = reference.scenario_id; reference.version = 0;
  try {
    const data = await loadReferenceVersions(id);
    if (reference.scenario_id !== id || !scenarioRefs.value.includes(reference)) return;
    reference.version = data.reduce((latest, item) => Math.max(latest, item.version), 0);
  } catch { /* Keep the row and explicit error; never invent a published version. */ }
}

const changeNote = ref(''), versions = ref<Version[]>([]), chosenVersion = ref(0);
const runParameters = ref('{}'), liveConfirmed = ref(false), runEnvironment = ref(''), build = ref('');
const environments = ref<Profile[]>([]), identities = ref<Profile[]>([]), bindings = ref<Profile[]>([]), scenarioOptions = ref<Asset[]>([]);
const savedDraft = ref('');
const search = ref('');
const filteredAssets = computed(() => {
  const query = search.value.trim().toLocaleLowerCase();
  return assets.value.filter(item => [item.draft.name, item.id, ...(item.draft.tags || [])].join(' ').toLocaleLowerCase().includes(query));
});
// 切换资产和新建都可能丢失编辑中的草稿，统一在入口确认。
function canLeaveDraft() { return !dirty.value || window.confirm('有未保存的修改，确认放弃并切换草稿？'); }
function createDraft() { if (canLeaveDraft()) newDraft(); }
async function chooseAsset(asset: Asset) { if (asset.id === selected.value?.id || !canLeaveDraft()) return; await action(() => select(asset)); }

const availableIdentities = computed(() => identities.value.filter(item => item.target_ids?.includes(targetRef.value)));
const availableBindings = computed(() => bindings.value.filter(item => item.target_id === targetRef.value && (!identityRef.value || item.identity_id === identityRef.value)));
const dirty = computed(() => { try { return JSON.stringify(draftData()) !== savedDraft.value; } catch { return true; } });
const rows = (value: unknown): Pair[] => Object.entries((value || {}) as Record<string, unknown>).map(([key, value]) => ({ key, value: typeof value === 'object' ? JSON.stringify(value) : String(value), original: value }));
function fields(pairs: Pair[]) {
  const result: Record<string, unknown> = {};
  for (const pair of pairs) { if (!pair.key.trim()) throw new Error('字段名称不能为空'); if (pair.key in result) throw new Error('字段名称不能重复'); const originalText = typeof pair.original === 'object' ? JSON.stringify(pair.original) : String(pair.original); result[pair.key] = 'original' in pair && pair.value === originalText ? pair.original : pair.value; }
  return result;
}
const importSource = ref(''), importKind = ref('legacy'), importText = ref('{}');
const expectedUserId = ref('');
const datasources = ref<BusinessDatasource[]>([]), datasourceRef = ref('');
const datasourceLoading = ref(false), datasourcesLoaded = ref(false), datasourceError = ref('');
const datasourcePreflight = ref<DatasourcePreflight | null>(null);
const receptionReady = computed(() => Boolean(targetRef.value && identityRef.value && bindingRef.value && expectedUserId.value.trim() && datasourceRef.value));
let datasourceSequence = 0;
// 预检仅证明当时选择的来源/身份/项目，切换后不继续展示旧绿灯。
watch([targetRef, identityRef, bindingRef, expectedUserId, datasourceRef], () => { datasourcePreflight.value = null; });
function datasourceStatus(value: string) { return ({ passed: '通过', failed: '失败', not_verified: '未验证', not_required: '无需验证' } as Record<string, string>)[value] || value; }
async function loadDatasources() {
  if (datasourceLoading.value) return;
  const sequence = ++datasourceSequence;
  datasourceLoading.value = true; datasourceError.value = ''; datasourcePreflight.value = null;
  try {
    const result = await apiClient.get<BusinessDatasource[]>('/business-datasources');
    if (sequence !== datasourceSequence) return;
    datasources.value = result; datasourcesLoaded.value = true;
    if (!result.some(source => source.id === datasourceRef.value)) datasourceRef.value = '';
  } catch (cause) { datasourceError.value = resolveApiErrorMessage(cause, '读取业务数据源失败'); }
  finally { if (sequence === datasourceSequence) datasourceLoading.value = false; }
}
function onReceptionToggle(event: Event) { if ((event.target as HTMLDetailsElement).open && !datasourcesLoaded.value) void loadDatasources(); }
const receptionPayload = () => ({ target_ref: targetRef.value, identity_ref: identityRef.value, binding_ref: bindingRef.value, expected_user_id: expectedUserId.value.trim(), datasource_ref: datasourceRef.value });
async function preflightDatasource(executeQuery: boolean) { await action(async () => {
  const selection = JSON.stringify(receptionPayload());
  const result = await apiClient.post<DatasourcePreflight>(`/business-datasources/${encodeURIComponent(datasourceRef.value)}/preflight`, { ...receptionPayload(), execute_query: executeQuery });
  if (selection === JSON.stringify(receptionPayload())) datasourcePreflight.value = result;
}); }
async function importReceptions() { await action(async () => {
  const result = await apiClient.post<{ assets: Asset[]; note: string }>('/imports/yanji-reception', receptionPayload());
  await load();
  message.value = `接诊筛选回归草稿已就绪（${result.assets.length} 条）；已有草稿保留原编辑。请选择场景，预检后发布和执行。`;
}); }
const collection = () => props.kind === 'suites' ? '/suite-assets' : '/scenarios';
const url = () => `/${props.kind}/${selected.value?.id}`;
const split = (value: string) => value.split(',').map(v => v.trim()).filter(Boolean);
const parse = (value: string) => JSON.parse(value);
function newDraft() {
  ++selectionSequence; settingsOpen.value = true; collapsed.value = []; debugOpen.value = false;
  selected.value = null; name.value = ''; priority.value = 'P1'; tags.value = 'core';
  steps.value = []; scenarioRefs.value = []; versions.value = []; chosenVersion.value = 0;
  targetRef.value = identityRef.value = bindingRef.value = ''; moduleName.value = '未分类'; budget.value = 300;
  runEnvironment.value = build.value = changeNote.value = message.value = error.value = ''; runParameters.value = '{}';
  parametersSchema.value = parameters.value = draftExtras.value = '{}'; checkResult.value = ''; liveConfirmed.value = false; savedDraft.value = JSON.stringify(draftData());
}
function addStep() {
  steps.value.push({ step_id: uniqueStepId(), name: '新步骤', phase: 'verify', type: 'http',
    method: 'GET', url: '{{host}}/api/v1/...', operation_kind: 'query', contract_confirmed: false,
    dependenciesText: '', safe_to_replay: false, bodyText: 'null', bodyType: 'none', headerRows: [], queryRows: [],
    assertionsText: '[{"name":"business-code","selector":"code","expected":200}]', extractorsText: '[]',
    waitConfirmed:false, stateSelector:'data.state', stateMapText:'{"pending":"pending","running":"running","success":"succeeded","failed":"failed"}',
    pollInterval:2, pollDeadline:60, pollAttempts:30, networkRetries:0, waitPolicyText:'{}' });
}
let selectionSequence = 0;
async function select(asset: Asset) {
  const sequence = ++selectionSequence;
  selected.value = asset; settingsOpen.value = false; emit('selected', asset.id); collapsed.value = []; debugOpen.value = false; const d = asset.draft;
  name.value = d.name; priority.value = d.priority; tags.value = (d.tags || []).join(',');
  targetRef.value = d.target_ref || ''; identityRef.value = d.identity_ref || ''; bindingRef.value = d.identity_binding_ref || '';
  moduleName.value = d.module || ''; parametersSchema.value = JSON.stringify(d.parameters_schema || {}, null, 2);
  parameters.value = JSON.stringify(d.parameters || {}, null, 2);
  draftExtras.value = JSON.stringify({ source: d.source || {}, migration_warnings: d.migration_warnings || [], migration_blockers: d.migration_blockers || [], fixtures: d.fixtures || [] }, null, 2);
  steps.value = (d.steps || []).map((s: Step) => ({...s, dependenciesText: s.depends_on.join(','),
    method: s.request.method, url: s.request.url, bodyText: s.request.body_type === 'raw' ? String(s.request.body ?? '') : JSON.stringify(s.request.body, null, 2),
    bodyType: String(s.request.body_type || 'none'), headerRows: rows(s.request.headers), queryRows: rows(s.request.query),
    assertionsText: JSON.stringify(s.assertions, null, 2), extractorsText: JSON.stringify(s.extractors, null, 2),
    waitConfirmed:s.wait_policy?.contract_confirmed === true, stateSelector:String(s.wait_policy?.state_selector || 'data.state'),
    stateMapText:JSON.stringify(s.wait_policy?.state_map || {},null,2), pollInterval:Number(s.wait_policy?.interval_seconds ?? 2),
    pollDeadline:Number(s.wait_policy?.deadline_seconds ?? 60),pollAttempts:Number(s.wait_policy?.max_attempts ?? 30),
    networkRetries:Number(s.wait_policy?.network_retries ?? 0),waitPolicyText:JSON.stringify(s.wait_policy || {},null,2) }));
  // API 列表进入 ref 后是 Vue Proxy，按引用契约复制字段，避免 structuredClone 抛错。
  scenarioRefs.value = (d.scenarios || []).map(ref => ({ scenario_id: ref.scenario_id, version: ref.version }));
  for (const reference of scenarioRefs.value) void loadReferenceVersions(reference.scenario_id).catch(() => {});
  budget.value = d.timeout_seconds || 300;
  savedDraft.value = JSON.stringify(draftData());
  const loadedVersions = await apiClient.get<Version[]>(url() + '/versions');
  if (sequence !== selectionSequence) return;
  versions.value = loadedVersions; chosenVersion.value = versions.value[0]?.version || 0;
  checkResult.value = ''; liveConfirmed.value = false; runParameters.value = '{}'; runEnvironment.value = build.value = changeNote.value = '';
}
let loadSequence = 0;
async function load() {
  const sequence = ++loadSequence;
  
  busy.value = true; error.value = '';
  try {
    const data = await Promise.all([apiClient.get<Asset[]>(collection()), apiClient.get<Profile[]>('/targets'), apiClient.get<Profile[]>('/identity-profiles'), apiClient.get<Profile[]>('/context-bindings'), apiClient.get<Profile[]>('/environments'), apiClient.get<Asset[]>('/scenarios')]);
    if (sequence !== loadSequence) return;
    [assets.value, targets.value, identities.value, bindings.value, environments.value, scenarioOptions.value] = data;
  }
  catch (cause) { if (sequence === loadSequence) error.value = resolveApiErrorMessage(cause, '资产更新失败；保留上次目录。'); }
  finally { if (sequence === loadSequence) busy.value = false; }
}
function draftData(locate = false): Data {
  const base = { ...selected.value?.draft, ...(props.kind === 'scenarios' ? parse(draftExtras.value) : {}), name: name.value, priority: priority.value, tags: split(tags.value) };
  if (props.kind === 'suites') return {...base, scenarios: scenarioRefs.value, timeout_seconds: budget.value};
  return { ...base, target_ref: targetRef.value, identity_ref: identityRef.value || null,
    identity_binding_ref: bindingRef.value || null, module: moduleName.value,
    parameters_schema: parse(parametersSchema.value), parameters: parse(parameters.value),
    steps: steps.value.map((s, index) => {
      const at = <T,>(field: string, operation: () => T): T => { try { return operation(); } catch (cause) { if (locate) void focusStep(index, field); throw new Error(`步骤 ${index + 1} (${s.step_id}) · ${field}: ${cause instanceof Error ? cause.message : '格式错误'}`); } };
      const json = (text: string, field: string, array = false) => at(field, () => { const result = parse(text); if (array && !Array.isArray(result)) throw new Error('必须为数组'); return result; });
      const { dependenciesText, method, url, headerRows, queryRows, bodyType, bodyText, assertionsText, extractorsText,
        waitConfirmed,stateSelector,stateMapText,pollInterval,pollDeadline,pollAttempts,networkRetries,waitPolicyText,...original } = s;
      return { ...original, depends_on: split(dependenciesText), request: { ...s.request, method, url, headers: at('请求头', () => fields(headerRows)), query: at('查询参数', () => fields(queryRows)), body_type: bodyType, body: bodyType === 'none' ? null : bodyType === 'raw' ? bodyText : json(bodyText, '请求体') },
        assertions: json(assertionsText, '断言 JSON', true), extractors: json(extractorsText, '变量提取 JSON', true),
        wait_policy:s.type === 'wait_until' ? {...json(waitPolicyText, '等待策略 JSON'),contract_confirmed:waitConfirmed,state_selector:stateSelector,
          state_map:json(stateMapText, '状态映射 JSON'),interval_seconds:pollInterval,deadline_seconds:pollDeadline,max_attempts:pollAttempts,network_retries:networkRetries} : null };
    }) };
}
function validatedDraft(): Data {
  const draft = draftData(true);
  const seen = new Set<string>();
  for (const [index, step] of (draft.steps || []).entries()) {
    const fail = (message: string) => { void focusStep(index, '依赖'); throw new Error(`步骤 ${index + 1} (${step.step_id}) · 依赖: ${message}`); };
    if (!step.step_id || seen.has(step.step_id)) fail('稳定 ID 不能为空或重复');
    for (const id of step.depends_on) if (!seen.has(id)) fail(`依赖 ${id} 不存在或位于当前步骤之后，请调整顺序`);
    seen.add(step.step_id);
  }
  return draft;
}
async function action(operation: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true; error.value = ''; message.value = '';
  try { await operation(); } catch (cause) { error.value = resolveApiErrorMessage(cause, '操作失败'); }
  finally { busy.value = false; }
}
async function refreshVersions(assetId: string) {
  const data = await apiClient.get<Version[]>(`/${props.kind}/${assetId}/versions`);
  if (selected.value?.id !== assetId) return;
  versions.value = data; chosenVersion.value = data[0]?.version || 0;
}
async function save() { await action(async () => {
  // Freeze before awaiting: the persisted baseline must never include edits typed in flight.
  const submitted = JSON.parse(JSON.stringify(validatedDraft())) as Data;
  if (props.kind === 'suites') {
    for (const reference of submitted.scenarios || []) {
      const published = await loadReferenceVersions(reference.scenario_id);
      if (!published.some(item => item.version === reference.version)) throw new Error(`场景 ${reference.scenario_id} 的 v${reference.version} 未发布，请重新选择固定版本`);
    }
  }
  const asset = selected.value ? await apiClient.patch<Asset>(url() + '/draft', { expected_revision: selected.value.revision, draft: submitted })
    : await apiClient.post<Asset>(collection(), submitted);
  selected.value = asset;
  // Mirror draftData's server base + submitted editor fields, including server-added defaults.
  // Never derive this baseline from the live buffer: it may already contain newer edits.
  savedDraft.value = JSON.stringify({ ...asset.draft, ...submitted });
  emit('selected', asset.id); emit('saved', { id: asset.id });
  await refreshVersions(asset.id); await load(); message.value = '草稿已持久保存；尚未发布。';
}); }
async function preflight() { await action(async () => { if (dirty.value) throw new Error('请先保存修改'); checkResult.value = JSON.stringify(await apiClient.post(url() + '/preflight'), null, 2); }); }
async function publish() { await action(async () => {
  if (dirty.value) throw new Error('请先保存修改');
  await apiClient.post(url() + '/publish', { expected_revision: selected.value?.revision, change_note: changeNote.value });
  if (selected.value) await refreshVersions(selected.value.id); message.value = '发布版本已冻结，编辑草稿不会改写它。';
}); }
async function copyAsset() { await action(async () => { const copy = await apiClient.post<Asset>(url() + '/copy'); await load(); await select(copy); }); }
async function archive() { await action(async () => { await apiClient.post(`${url()}/archive?revision=${selected.value?.revision}`); newDraft(); await load(); }); }
const runData = () => ({ transport_mode: 'live', parameters: parse(runParameters.value), environment_id: runEnvironment.value || null, build: build.value.trim() || 'unspecified' });
async function plan() { await action(async () => { checkResult.value = JSON.stringify(await apiClient.post(`${url()}/versions/${chosenVersion.value}/plan`, runData()), null, 2); }); }
async function run() { if (busy.value || !canLeaveDraft()) return; await action(async () => { const result = await apiClient.post<{run_id: string}>(`${url()}/versions/${chosenVersion.value}/runs`, runData()); formalNavigation.value = true; try { await router.push({name: 'runs', query: {runId: result.run_id}}); } finally { formalNavigation.value = false; } }); }
async function exportAsset() { await action(async () => { checkResult.value = JSON.stringify(await apiClient.get(`${url()}/versions/${chosenVersion.value}/export`), null, 2); }); }
async function importAsset() { await action(async () => {
  const body = importKind.value === 'standard' ? parse(importText.value)
    : { target_ref: targetRef.value, yaml_text: importSource.value };
  const result = await apiClient.post<Asset | {asset: Asset; report: unknown}>(`/imports/${importKind.value}`, body);
  await load(); await select('asset' in result ? result.asset : result);
  checkResult.value = JSON.stringify('asset' in result ? result.report : {}, null, 2);
}); }
async function showYanjiContracts() { await action(async () => { checkResult.value = JSON.stringify(await apiClient.get('/regression-packs/yanji'), null, 2); }); }
async function importYanji() { await action(async () => {
  await apiClient.post('/imports/yanji-query', {target_ref: targetRef.value, identity_ref: identityRef.value, binding_ref: bindingRef.value, expected_user_id: expectedUserId.value});
  await load(); message.value = '查询草稿已创建；请选择场景，预检后发布和执行。';
}); }
savedDraft.value = JSON.stringify(draftData());
onMounted(async () => {
  window.addEventListener('beforeunload', beforeUnload);
  await load();
  const first = assets.value.find(item => item.id === route.query.assetId) || assets.value[0];
  if (first && !selected.value && !dirty.value) await action(() => select(first));
});
watch(() => route.query.assetId, async id => {
  if (typeof id !== 'string' || id === selected.value?.id) return;
  const asset = assets.value.find(item => item.id === id);
  if (asset) await action(() => select(asset));
});
</script>

<style scoped>
.settings-content { display: grid; gap: 12px; padding: 4px 12px 12px; min-width: 0; }
.step-content { display: grid; gap: 12px; min-width: 0; }
.step-navigation { display: flex; flex-wrap: wrap; gap: 6px; }
.asset-panel { min-width: 0; display: grid; gap: 16px; }
.asset-header { display: flex; justify-content: space-between; flex-wrap: wrap; align-items: center; gap: 12px; padding: 18px 22px; border: 1px solid var(--color-border); border-radius: var(--radius-large); background: white; }
.asset-header h2 { display: flex; gap: 10px; align-items: center; margin: 0; font-size: 16px; }
.asset-header p { margin: 3px 0 0; font-size: 12px; color: var(--color-ink-subtle); }
.count-badge { padding: 2px 7px; border-radius: 5px; color: var(--color-ink-subtle); background: #f1f3f7; font-size: 11px; font-weight: 500; }
.asset-grid { display: grid; grid-template-columns: 248px minmax(0, 1fr); align-items: start; gap: 20px; }
.asset-library { min-width: 0; background: white; border: 1px solid var(--color-border); border-radius: var(--radius-large); overflow: clip; }
.asset-search { display: grid; gap: 8px; padding: 16px; }
.asset-search > span { font-size: 13px; color: var(--color-ink-base); font-weight: 600; }
.asset-search input { font-size: 12px; background: #fafbfc; }
.asset-library__count { margin: 0; padding: 0 16px 12px; color: var(--color-ink-subtle); font-size: 11px; border-bottom: 1px solid var(--color-border); }
.asset-list { margin: 0; padding: 8px; list-style: none; max-height: 65vh; overflow-y: auto; }
.asset-list__item { display: grid; justify-content: stretch; gap: 8px; width: 100%; padding: 13px 12px; border: 1px solid transparent; text-align: left; background: white; }
.asset-list__item--selected { background: var(--color-accent-soft); border-color: #d5defd; }
.asset-list__item:hover:not(:disabled) { background: #f5f7fe; border-color: #d5defd; }
.asset-list__name { color: var(--color-ink-base); font-size: 13px; font-weight: 600; overflow-wrap: anywhere; }
.asset-list__meta { display: flex; gap: 10px; align-items: center; color: var(--color-ink-subtle); font-size: 11px; }
.asset-priority { color: var(--color-accent-strong); font: 11px var(--font-mono); background: #edf1fb; padding: 2px 5px; border-radius: 3px; }
.asset-list__tags { font-size: 11px; color: var(--color-ink-subtle); overflow-wrap: anywhere; }
.asset-empty { padding: 18px 16px 24px; text-align: center; font-size: 12px; color: var(--color-ink-subtle); }
.asset-empty strong { font-size: 13px; color: var(--color-ink-muted); }
.asset-form { display: grid; gap: 12px; min-width: 0; padding: 16px; background: white; border: 1px solid var(--color-border); border-radius: var(--radius-large); }
.editor-heading { position: sticky; top: 0; z-index: 3; background: white; padding-top: 8px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 12px; padding-bottom: 18px; border-bottom: 1px solid var(--color-border); }
.editor-heading > div { min-width: 0; }
.editor-heading h3 { margin: 5px 0 0; font-size: 18px; overflow-wrap: anywhere; }
.editor-eyebrow { font-size: 11px; color: var(--color-ink-subtle); }
.draft-state { flex-shrink: 0; color: #697586; background: #f4f5f7; padding: 3px 8px; border-radius: 5px; font-size: 11px; }
.form-section-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; font-size: 13px; font-weight: 650; }
.form-section-title small { color: var(--color-ink-subtle); font-weight: 400; font-size: 11px; }
.editor-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.editor-fields > label:first-child:last-child { grid-column: 1 / -1; }
label { display: grid; gap: 6px; min-width: 0; }
.editor-details { min-width: 0; border: 1px solid var(--color-border); border-radius: var(--radius-medium); background: #fcfcfd; }
.editor-details summary span { font-weight: 400; color: var(--color-ink-subtle); font-size: 11px; margin-left: 7px; }
.editor-details > .editor-fields, .advanced-fields { padding: 4px 14px 16px; }
.advanced-fields { display: grid; gap: 14px; }
.step-card { display: grid; min-width: 0; gap: 18px; border-color: #dce2ef; }
.step-card legend { color: var(--color-accent-strong); }
.step-card fieldset { display: grid; gap: 10px; background: white; }
.step-delete { justify-self: end; }
.step-empty { margin: 0; padding: 24px 16px; border: 1px dashed #d6dce7; border-radius: 7px; color: var(--color-ink-subtle); font-size: 13px; text-align: center; }
.request-row { display: flex; flex-wrap: wrap; gap: 8px; }
.request-row input { flex: 1 1 8rem; }
.asset-id { margin: 0; color: var(--color-ink-subtle); font: 11px/1.7 var(--font-mono); overflow-wrap: anywhere; }
.editor-save-bar { display: flex; flex-wrap: wrap; gap: 8px; padding: 16px 0; border-top: 1px solid var(--color-border); border-bottom: 1px solid var(--color-border); }
.publish-section { display: grid; gap: 12px; }
.publish-section button { justify-self: start; }
.version-section { display: grid; gap: 16px; padding: 22px; border: 1px solid var(--color-border); border-radius: var(--radius-large); background: white; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 35rem; }
.asset-imports { display: grid; gap: 8px; }
.asset-imports details { border: 1px solid var(--color-border); border-radius: var(--radius-medium); background: white; }
.asset-imports p { font-size: 12px; color: var(--color-ink-subtle); }
@media(max-width:1200px) { .asset-grid { grid-template-columns: 210px minmax(0, 1fr); gap: 16px; } }
@media(max-width:760px) { .asset-grid { grid-template-columns: minmax(0, 1fr); } .asset-form { padding: 18px; } .asset-list { max-height: 240px; } }
@media(max-width:540px) { .editor-fields { grid-template-columns: minmax(0, 1fr); } .asset-header { padding: 16px; } .asset-form { padding: 16px; } .step-card { padding: 12px; } .version-section { padding: 16px; } }
</style>
