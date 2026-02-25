<template>
  <div>
    <!-- Header -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
      <h1 style="font-size: 1.5rem; font-weight: 700;">📋 账号管理</h1>
      <div style="display: flex; gap: 10px;">
        <button class="btn btn-secondary" @click="showGroupModal = true">📁 管理分组</button>
        <button class="btn btn-secondary" @click="startRefreshAll" :disabled="refreshingAll">🔁 {{ refreshingAll ? '刷新中...' : '全量刷新Token' }}</button>
        <button class="btn btn-secondary" @click="showSettingsModal = true">⚙️ 设置</button>
        <button class="btn btn-secondary" @click="showBatchModal = true">📥 批量导入</button>
        <button class="btn btn-secondary" @click="handleExport">📤 导出</button>
        <button class="btn btn-primary" @click="showAddModal = true">➕ 添加账号</button>
      </div>
    </div>

    <!-- Group Filter Tabs -->
    <div class="account-selector" style="margin-bottom: 20px;">
      <div
        class="account-chip"
        :class="{ active: filterGroupId === null }"
        @click="filterByGroup(null)"
      >全部</div>
      <div
        class="account-chip"
        :class="{ active: filterGroupId === 0 }"
        @click="filterByGroup(0)"
      >未分组</div>
      <div
        v-for="group in groups"
        :key="group.id"
        class="account-chip"
        :class="{ active: filterGroupId === group.id }"
        @click="filterByGroup(group.id)"
      >
        <span v-if="group.color" :style="{display:'inline-block',width:'8px',height:'8px',borderRadius:'50%',background:group.color,marginRight:'4px'}"></span>
        {{ group.name }}
        <span v-if="group.proxy_url" style="font-size:0.7rem;margin-left:2px;">🌐</span>
        <span class="chip-unread" v-if="group.account_count > 0">{{ group.account_count }}</span>
      </div>
    </div>

    <!-- Search Bar -->
    <div class="search-bar" style="margin-bottom: 20px;">
      <div style="display: flex; gap: 10px; align-items: center;">
        <select class="form-input" v-model="searchGroupId" style="width: auto; min-width: 120px; padding: 8px 12px;">
          <option :value="null">全部分组</option>
          <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
        </select>
        <input
          class="form-input"
          v-model="searchAccountEmail"
          placeholder="搜索账号邮箱..."
          style="width: 200px;"
          @keyup.enter="handleSearch"
        />
        <input
          class="form-input"
          v-model="searchKeyword"
          placeholder="🔍 搜索邮件主题..."
          style="flex: 1;"
          @keyup.enter="handleSearch"
        />
        <button class="btn btn-primary" @click="handleSearch" :disabled="searchStore.loading">
          {{ searchStore.loading ? '搜索中...' : '🔍 搜索' }}
        </button>
        <button v-if="searchStore.searched" class="btn btn-secondary" @click="clearSearch">✕ 清除</button>
      </div>
    </div>

    <!-- Search Results -->
    <div v-if="searchStore.searched" class="card" style="margin-bottom: 20px;">
      <div class="card-header">
        <h2>🔍 搜索结果 ({{ searchStore.total }})</h2>
        <span style="color: var(--text-muted); font-size: 0.85rem;">
          关键词: "{{ searchStore.keyword }}"
        </span>
      </div>
      <div class="card-body" style="padding: 0;">
        <div v-if="searchStore.loading" class="loading-center">
          <div class="spinner"></div>
        </div>
        <div v-else-if="searchStore.results.length === 0" class="empty-state">
          <div class="empty-state-icon">🔍</div>
          <div class="empty-state-text">没有找到匹配的邮件</div>
        </div>
        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>账号</th>
                <th>主题</th>
                <th>发件人</th>
                <th>时间</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="email in searchStore.results"
                :key="email.id"
                @click="openSearchEmail(email)"
                style="cursor: pointer;"
                class="search-result-row"
              >
                <td style="font-size: 0.82rem; color: var(--accent-light); white-space: nowrap;">{{ email.account_email }}</td>
                <td style="font-weight: 500; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ email.subject || '(无主题)' }}</td>
                <td style="font-size: 0.85rem;">{{ email.sender_name || email.sender_address || '未知' }}</td>
                <td style="font-size: 0.82rem; color: var(--text-muted); white-space: nowrap;">{{ formatTime(email.received_at) }}</td>
                <td>
                  <span :style="{ color: email.is_read ? 'var(--text-muted)' : 'var(--accent-light)', fontWeight: email.is_read ? 400 : 600 }">
                    {{ email.is_read ? '已读' : '未读' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <!-- Pagination -->
          <div v-if="searchStore.total > searchStore.pageSize" style="display: flex; justify-content: center; gap: 10px; padding: 16px;">
            <button
              class="btn btn-secondary btn-sm"
              :disabled="searchStore.page <= 1"
              @click="searchStore.search(searchStore.keyword, searchStore.groupId, searchStore.page - 1, searchAccountEmail)"
            >← 上一页</button>
            <span style="line-height: 30px; color: var(--text-muted); font-size: 0.85rem;">
              第 {{ searchStore.page }} / {{ Math.ceil(searchStore.total / searchStore.pageSize) }} 页
            </span>
            <button
              class="btn btn-secondary btn-sm"
              :disabled="searchStore.page >= Math.ceil(searchStore.total / searchStore.pageSize)"
              @click="searchStore.search(searchStore.keyword, searchStore.groupId, searchStore.page + 1, searchAccountEmail)"
            >下一页 →</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Batch Action Bar -->
    <div v-if="selectedIds.length > 0" class="batch-bar">
      <span>已选中 <strong>{{ selectedIds.length }}</strong> 个账号</span>
      <div style="display: flex; align-items: center; gap: 8px;">
        <span>移动到:</span>
        <select class="form-input" v-model="batchMoveGroupId" style="width: auto; padding: 4px 8px; font-size: 0.85rem; min-width: 120px;">
          <option :value="null">未分组</option>
          <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
        </select>
        <button class="btn btn-primary btn-sm" @click="handleBatchMove" :disabled="batchMoving">
          {{ batchMoving ? '移动中...' : '确认移动' }}
        </button>
        <button class="btn btn-secondary btn-sm" @click="handleBatchCheckProtocols" :disabled="batchChecking">
          {{ batchChecking ? '🔍 检测中...' : '🔍 检测协议' }}
        </button>
        <button class="btn btn-secondary btn-sm" @click="handleExportSelected">📥 导出选中</button>
        <button class="btn btn-secondary btn-sm" @click="selectedIds = []">取消选择</button>
      </div>
    </div>

    <!-- Account Table -->
    <div class="card">
      <div class="card-header">
        <h2>账号列表 ({{ filteredAccounts.length }})</h2>
        <button class="btn btn-secondary btn-sm" @click="refreshAll" :disabled="loading || syncing">
          {{ syncing ? '⏳ 同步中...' : '🔄 刷新' }}
        </button>
      </div>
      <div class="card-body" style="padding: 0;">
        <div v-if="loading" class="loading-center">
          <div class="spinner"></div>
        </div>

        <div v-else-if="filteredAccounts.length === 0" class="empty-state">
          <div class="empty-state-icon">📭</div>
          <div class="empty-state-text">暂无账号</div>
          <div class="empty-state-hint">点击「添加账号」或「批量导入」开始</div>
        </div>

        <div v-else class="table-wrap">
          <table>
            <thead>
              <tr>
                <th style="width: 36px;">
                  <input type="checkbox" :checked="allSelected" @change="toggleSelectAll" />
                </th>
                <th>邮箱地址</th>
                <th>备注</th>
                <th>分组</th>
                <th>状态</th>
                <th>协议</th>
                <th>未读</th>
                <th>上次同步</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="account in filteredAccounts" :key="account.id" :class="{ 'row-active': emailViewAccount && emailViewAccount.id === account.id }">
                <td>
                  <input type="checkbox" :value="account.id" v-model="selectedIds" />
                </td>
                <td :style="{fontWeight: account.refresh_status==='failed' ? 700 : 500, color: account.refresh_status==='failed' ? '#ef4444' : 'inherit'}">{{ account.email }}</td>
                <td style="font-size:0.8rem;color:var(--text-muted);max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" :title="account.remark">{{ account.remark || '—' }}</td>
                <td>
                  <select
                    class="form-input"
                    style="width: auto; padding: 4px 8px; font-size: 0.8rem; min-width: 90px;"
                    :value="account.group_id || ''"
                    @change="changeGroup(account.id, $event.target.value)"
                  >
                    <option value="">未分组</option>
                    <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
                  </select>
                </td>
                <td>
                  <span class="badge" :class="'badge-' + account.status">
                    <span class="badge-dot"></span>
                    {{ statusText(account.status) }}
                  </span>
                </td>
                <td>
                  <div style="display: flex; gap: 4px; flex-wrap: wrap;">
                    <span v-if="account.imap_enabled" class="protocol-tag protocol-ok">IMAP</span>
                    <span v-if="account.pop3_enabled" class="protocol-tag protocol-ok">POP3</span>
                    <span v-if="account.graph_enabled" class="protocol-tag protocol-ok">Graph</span>
                    <span v-if="!account.imap_enabled && !account.pop3_enabled && !account.graph_enabled" style="color: var(--text-muted); font-size: 0.8rem;">—</span>
                  </div>
                </td>
                <td>
                  <span v-if="account.unread_count > 0" style="color: var(--accent-light); font-weight: 600;">
                    {{ account.unread_count }}
                  </span>
                  <span v-else style="color: var(--text-muted);">0</span>
                </td>
                <td style="font-size: 0.82rem; color: var(--text-muted);">
                  {{ account.last_synced ? formatTime(account.last_synced) : '未同步' }}
                </td>
                <td>
                  <div style="display: flex; gap: 6px;">
                    <button
                      v-if="!account.refresh_token"
                      class="btn btn-sm" style="background:var(--accent);color:#fff;"
                      @click="authorizeAccount(account.id)"
                    >
                      🔗 授权
                    </button>
                    <button
                      class="btn btn-sm"
                      :class="emailViewAccount && emailViewAccount.id === account.id ? 'btn-primary' : 'btn-secondary'"
                      @click="toggleEmailView(account)"
                    >
                      📬 邮件
                    </button>
                    <button
                      class="btn btn-secondary btn-sm"
                      @click="checkProtocols(account)"
                      :disabled="account._checking"
                      title="检测协议"
                    >
                      {{ account._checking ? '⏳' : '🔍' }}
                    </button>
                    <button
                      class="btn btn-secondary btn-sm"
                      @click="syncOne(account.id)"
                      :disabled="account.status === 'syncing'"
                    >
                      🔄
                    </button>
                    <button
                      class="btn btn-danger btn-sm"
                      @click="confirmDelete(account)"
                    >
                      🗑
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Error Tooltips -->
    <div v-for="account in filteredAccounts.filter(a => a.status === 'error')" :key="'err-' + account.id"
      style="margin-top:12px; padding:12px 16px; background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.15); border-radius:8px; font-size:0.82rem; color:var(--danger);">
      ⚠️ {{ account.email }}: {{ account.last_error || '未知错误' }}
    </div>

    <!-- Email Modal Popup -->
    <Teleport to="body">
      <Transition name="email-modal">
        <div v-if="emailViewAccount" class="email-modal-overlay" @click.self="closeEmailModal">
          <div class="email-modal" :class="{ 'email-modal-detail': viewingDetail }">
            <!-- Modal Header -->
            <div class="email-modal-header">
              <div class="email-modal-title">
                <button v-if="viewingDetail" class="email-modal-back" @click="backToList">←</button>
                <div class="email-modal-avatar">{{ viewingDetail ? '📧' : '📬' }}</div>
                <div v-if="!viewingDetail">
                  <div class="email-modal-account">{{ emailViewAccount.email }}</div>
                  <div class="email-modal-subtitle">
                    {{ emailsStore.loading ? '加载中...' : `${emailList.length} 封邮件` }}
                    <span v-if="emailsStore.method" style="font-size:0.7rem;padding:1px 6px;background:rgba(99,102,241,0.15);border-radius:6px;color:var(--accent-light);">{{ emailsStore.method }}</span>
                    <span v-if="emailViewAccount.unread_count > 0" class="email-modal-unread-badge">
                      {{ emailViewAccount.unread_count }} 未读
                    </span>
                  </div>
                </div>
                <div v-else>
                  <div class="email-modal-account">{{ currentDetail?.subject || '(无主题)' }}</div>
                  <div class="email-modal-subtitle">{{ emailViewAccount.email }}</div>
                </div>
              </div>
              <div class="email-modal-actions">
                <button v-if="!viewingDetail" class="email-modal-btn" @click="refreshEmails" :disabled="emailsStore.loading" title="刷新">
                  <span :class="{ 'spin-icon': emailsStore.loading }">🔄</span>
                </button>
                <button class="email-modal-btn email-modal-close" @click="closeEmailModal" title="关闭">✕</button>
              </div>
            </div>

            <!-- Folder Tabs -->
            <div v-if="!viewingDetail" style="display:flex;gap:0;border-bottom:1px solid rgba(255,255,255,0.06);">
              <button v-for="f in folders" :key="f.value" @click="switchFolder(f.value)" :style="{padding:'10px 18px',fontSize:'0.82rem',border:'none',background:emailFolder===f.value?'rgba(99,102,241,0.1)':'transparent',color:emailFolder===f.value?'var(--accent-light)':'rgba(255,255,255,0.5)',borderBottom:emailFolder===f.value?'2px solid var(--accent)':'2px solid transparent',cursor:'pointer',transition:'all 0.2s'}">
                {{ f.icon }} {{ f.label }}
              </button>
            </div>

            <!-- Email List View -->
            <div v-if="!viewingDetail" class="email-modal-body">
              <div v-if="emailsStore.loading" class="email-modal-loading">
                <div class="spinner"></div>
              </div>
              <div v-else-if="emailsStore.error" class="email-modal-empty">
                <div style="font-size: 2.5rem; margin-bottom: 12px;">⚠️</div>
                <div style="color:var(--danger);font-weight:500;margin-bottom:8px;">获取邮件失败</div>
                <div style="font-size:0.82rem;color:var(--text-muted);max-width:400px;word-break:break-all;">
                  {{ typeof emailsStore.error === 'object' ? (emailsStore.error.message || JSON.stringify(emailsStore.error.errors)) : emailsStore.error }}
                </div>
                <button class="btn btn-primary btn-sm" style="margin-top:14px;" @click="refreshEmails">🔄 重试</button>
              </div>
              <div v-else-if="emailList.length === 0" class="email-modal-empty">
                <div style="font-size: 2.5rem; margin-bottom: 12px;">📭</div>
                <div>暂无邮件</div>
              </div>
              <div v-else class="email-items">
                <div
                  v-for="email in emailList"
                  :key="email.id"
                  class="email-item"
                  :class="{ 'email-item-unread': !email.is_read }"
                  @click="openEmail(email)"
                >
                  <div class="email-item-indicator" v-if="!email.is_read"></div>
                  <div class="email-item-avatar">
                    {{ (email.sender?.name || email.sender?.address || '?')[0].toUpperCase() }}
                  </div>
                  <div class="email-item-content">
                    <div class="email-item-top">
                      <span class="email-item-sender">{{ email.sender?.name || email.sender?.address || '未知' }}</span>
                      <span class="email-item-time">{{ formatEmailTime(email.received_at) }}</span>
                    </div>
                    <div class="email-item-subject">{{ email.subject || '(无主题)' }}</div>
                    <div class="email-item-preview">{{ email.preview || '' }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Email Detail View -->
            <div v-else class="email-modal-body email-detail-view">
              <div v-if="emailsStore.detailLoading" class="email-modal-loading">
                <div class="spinner"></div>
              </div>
              <template v-else-if="currentDetail">
                <!-- Detail Meta -->
                <div class="email-detail-meta">
                  <div class="email-detail-meta-row">
                    <span class="email-detail-label">发件人</span>
                    <span>{{ currentDetail.sender?.name || '' }} &lt;{{ currentDetail.sender?.address || '' }}&gt;</span>
                  </div>
                  <div class="email-detail-meta-row">
                    <span class="email-detail-label">收件人</span>
                    <span>
                      <template v-for="(r, i) in currentDetail.to_recipients" :key="i">
                        {{ r.name || r.address }}{{ i < currentDetail.to_recipients.length - 1 ? ', ' : '' }}
                      </template>
                    </span>
                  </div>
                  <div class="email-detail-meta-row">
                    <span class="email-detail-label">时间</span>
                    <span>{{ formatDetailTime(currentDetail.received_at) }}</span>
                  </div>
                  <div v-if="currentDetail.has_attachments" class="email-detail-meta-row">
                    <span class="email-detail-label">附件</span>
                    <span style="color: var(--accent-light);">📎 包含附件</span>
                  </div>
                </div>
                <!-- Detail Body -->
                <div class="email-detail-body">
                  <iframe
                    v-if="currentDetail.body_html"
                    :srcdoc="bodyWithStyle"
                    sandbox="allow-same-origin"
                    referrerpolicy="no-referrer"
                  ></iframe>
                  <div v-else class="email-modal-empty" style="padding: 30px;">
                    (无邮件内容)
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Add Account Modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>添加账号</h3>
          <button class="btn btn-icon btn-secondary" @click="showAddModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">所属分组</label>
            <select class="form-input" v-model="form.group_id">
              <option :value="null">未分组</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">邮箱地址</label>
            <input class="form-input" v-model="form.email" placeholder="user@outlook.com" />
          </div>
          <div class="form-group">
            <label class="form-label">密码</label>
            <input class="form-input" v-model="form.password" type="password" placeholder="密码" />
          </div>
          <div class="form-group">
            <label class="form-label">Client ID <span style="color:var(--text-muted);font-weight:400">(可选)</span></label>
            <input class="form-input" v-model="form.client_id" placeholder="Azure App Client ID" />
          </div>
          <div class="form-group">
            <label class="form-label">Refresh Token <span style="color:var(--text-muted);font-weight:400">(可选)</span></label>
            <textarea class="form-textarea" v-model="form.refresh_token" rows="3" placeholder="Refresh Token"></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">备注 <span style="color:var(--text-muted);font-weight:400">(可选)</span></label>
            <input class="form-input" v-model="form.remark" placeholder="备注信息" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showAddModal = false">取消</button>
          <button class="btn btn-primary" @click="handleAdd" :disabled="adding">
            {{ adding ? '添加中...' : '确认添加' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Batch Import Modal -->
    <div v-if="showBatchModal" class="modal-overlay" @click.self="showBatchModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>批量导入</h3>
          <button class="btn btn-icon btn-secondary" @click="showBatchModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">导入到分组</label>
            <select class="form-input" v-model="batchGroupId">
              <option :value="null">未分组</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">账号列表</label>
            <textarea
              class="form-textarea"
              v-model="batchText"
              rows="8"
              placeholder="一行一个账号，格式：邮箱----密码 或 邮箱----密码----client_id----refresh_token"
            ></textarea>
            <div class="form-hint">
              格式: <code>邮箱----密码</code> 或 <code>邮箱----密码----client_id----refresh_token</code> 或 <code>邮箱----密码----client_id----refresh_token----备注</code>，每行一个
            </div>
          </div>

          <!-- Import Results -->
          <div v-if="batchResult" class="import-result">
            <h4>导入结果</h4>
            <div class="import-stats">
              <div class="import-stat">
                总计: <strong>{{ batchResult.total }}</strong>
              </div>
              <div class="import-stat" style="color: var(--success);">
                成功: <strong>{{ batchResult.success }}</strong>
              </div>
              <div class="import-stat" style="color: var(--danger);">
                失败: <strong>{{ batchResult.failed }}</strong>
              </div>
            </div>
            <ul v-if="batchResult.errors.length" class="import-errors">
              <li v-for="(err, i) in batchResult.errors" :key="i">{{ err }}</li>
            </ul>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showBatchModal = false">关闭</button>
          <button class="btn btn-primary" @click="handleBatchImport" :disabled="importing">
            {{ importing ? '导入中...' : '开始导入' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Group Management Modal -->
    <div v-if="showGroupModal" class="modal-overlay" @click.self="showGroupModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>📁 分组管理</h3>
          <button class="btn btn-icon btn-secondary" @click="showGroupModal = false">✕</button>
        </div>
        <div class="modal-body">
          <!-- Create Group -->
          <div style="display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap;">
            <input
              class="form-input"
              v-model="newGroupName"
              placeholder="新分组名称"
              @keyup.enter="handleCreateGroup"
              style="flex: 1; min-width: 120px;"
            />
            <input type="color" v-model="newGroupColor" style="width:36px;height:36px;border:none;border-radius:6px;cursor:pointer;padding:0;" title="分组颜色" />
            <input
              class="form-input"
              v-model="newGroupProxy"
              placeholder="代理URL (http/socks5)"
              style="min-width: 180px;"
            />
            <button class="btn btn-primary" @click="handleCreateGroup" :disabled="!newGroupName.trim()">
              创建
            </button>
          </div>

          <!-- Group List -->
          <div v-if="groups.length === 0" style="color: var(--text-muted); text-align: center; padding: 20px;">
            暂无分组
          </div>
          <div
            v-for="group in groups"
            :key="group.id"
            style="display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid var(--border);"
          >
            <div style="flex: 1;">
              <div style="display:flex;align-items:center;gap:6px;">
                <span v-if="group.color" :style="{display:'inline-block',width:'10px',height:'10px',borderRadius:'50%',background:group.color}"></span>
                <span style="font-weight: 500;">{{ group.name }}</span>
                <span v-if="group.proxy_url" style="font-size:0.72rem;padding:1px 6px;background:rgba(99,102,241,0.1);border-radius:4px;color:var(--accent-light);">{{ group.proxy_url }}</span>
              </div>
              <div style="font-size: 0.8rem; color: var(--text-muted);">
                {{ group.account_count }} 个账号
                <span v-if="group.description"> · {{ group.description }}</span>
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <button
                class="btn btn-sm btn-secondary"
                @click="editGroup(group)"
                title="编辑"
              >✏️</button>
              <button
                class="btn btn-sm"
                :class="group.auto_sync ? 'btn-primary' : 'btn-secondary'"
                @click="toggleAutoSync(group)"
                :title="group.auto_sync ? '点击关闭自动同步' : '点击开启自动同步'"
                style="font-size: 0.75rem; min-width: 90px;"
              >
                {{ group.auto_sync ? '🔄 自动同步' : '⏸ 不同步' }}
              </button>
              <button class="btn btn-danger btn-sm" @click="handleDeleteGroup(group.id)">🗑</button>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showGroupModal = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation -->
    <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
      <div class="modal" style="max-width: 400px;">
        <div class="modal-header">
          <h3>确认删除</h3>
        </div>
        <div class="modal-body">
          <p>确定要删除账号 <strong>{{ deleteTarget.email }}</strong> 吗？此操作不可恢复。</p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="deleteTarget = null">取消</button>
          <button class="btn btn-danger" @click="handleDelete" :disabled="deleting">
            {{ deleting ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Device Code Auth Modal -->
    <div v-if="deviceCode" class="modal-overlay" @click.self="cancelDeviceCode">
      <div class="modal" style="max-width: 420px; text-align: center;">
        <div class="modal-header">
          <h3>🔑 账号授权</h3>
          <button class="btn btn-icon btn-secondary" @click="cancelDeviceCode">✕</button>
        </div>
        <div class="modal-body">
          <p style="color:var(--text-muted); margin-bottom:16px;">请打开以下链接，输入验证码完成授权</p>
          <div style="font-size: 2rem; font-weight: 700; letter-spacing: 6px; color: var(--accent-light); background: rgba(99,102,241,0.08); padding: 16px; border-radius: 12px; margin-bottom: 16px; font-family: monospace;">
            {{ deviceCode.user_code }}
          </div>
          <a :href="deviceCode.verification_uri" target="_blank" class="btn btn-primary" style="display:inline-block; margin-bottom: 16px;">
            🌐 打开验证页面
          </a>
          <p style="color:var(--text-muted); font-size: 0.85rem;">
            <span v-if="deviceCodeStatus === 'pending'">⭐ 等待中，请在浏览器中完成登录授权...</span>
            <span v-else-if="deviceCodeStatus === 'success'" style="color:var(--success);">✅ 授权成功！</span>
            <span v-else-if="deviceCodeStatus === 'error'" style="color:var(--danger);">❌ {{ deviceCodeError }}</span>
          </p>
        </div>
      </div>
    </div>

    <!-- Settings Modal -->
    <div v-if="showSettingsModal" class="modal-overlay" @click.self="showSettingsModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>⚙️ 系统设置</h3>
          <button class="btn btn-icon btn-secondary" @click="showSettingsModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">修改密码</label>
            <input class="form-input" v-model="settingsOldPwd" type="password" placeholder="旧密码" style="margin-bottom:8px;" />
            <input class="form-input" v-model="settingsNewPwd" type="password" placeholder="新密码" />
          </div>
          <button class="btn btn-primary btn-sm" @click="handleChangePassword" style="margin-bottom:16px;">修改密码</button>
          <div class="form-group">
            <label class="form-label">GPTMail API Key</label>
            <input class="form-input" v-model="settingsApiKey" placeholder="API Key" />
          </div>
          <hr style="border-color:var(--border);margin:16px 0;" />
          <div class="form-group">
            <label class="form-label">定时刷新 Token</label>
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
              <label><input type="checkbox" v-model="refreshEnabled" /> 启用定时刷新</label>
            </div>
            <div v-if="refreshEnabled">
              <div style="display:flex;gap:8px;margin-bottom:8px;align-items:center;">
                <label><input type="radio" v-model="refreshMode" value="days" /> 按天数</label>
                <label><input type="radio" v-model="refreshMode" value="cron" /> Cron 表达式</label>
              </div>
              <input v-if="refreshMode==='days'" class="form-input" v-model="refreshDays" type="number" placeholder="每 N 天刷新一次" style="width:200px;" />
              <div v-else>
                <input class="form-input" v-model="refreshCron" placeholder="0 3 * * *" style="margin-bottom:4px;" />
                <div style="font-size:0.78rem;color:var(--text-muted);">示例: <code>0 3 * * *</code> 每天凌晨3点, <code>0 */6 * * *</code> 每6小时</div>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showSettingsModal = false">关闭</button>
          <button class="btn btn-primary" @click="saveSettings">保存设置</button>
        </div>
      </div>
    </div>

    <!-- Refresh Progress Modal -->
    <div v-if="refreshingAll" class="modal-overlay">
      <div class="modal" style="max-width: 500px;">
        <div class="modal-header">
          <h3>🔁 全量刷新 Token</h3>
        </div>
        <div class="modal-body">
          <div style="margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:4px;">
              <span>进度: {{ refreshProgress.current }} / {{ refreshProgress.total }}</span>
              <span>✅ {{ refreshProgress.success }} ❌ {{ refreshProgress.fail }}</span>
            </div>
            <div style="width:100%;height:8px;background:rgba(255,255,255,0.08);border-radius:4px;overflow:hidden;">
              <div :style="{width: refreshProgress.total ? (refreshProgress.current/refreshProgress.total*100)+'%' : '0%', height:'100%', background:'linear-gradient(90deg,#6366f1,#8b5cf6)', borderRadius:'4px', transition:'width 0.3s'}"></div>
            </div>
          </div>
          <div v-if="refreshProgress.lastEmail" style="font-size:0.82rem;color:var(--text-muted);">
            {{ refreshProgress.lastOk ? '✅' : '❌' }} {{ refreshProgress.lastEmail }}
            <span v-if="refreshProgress.lastError" style="color:var(--danger);"> - {{ refreshProgress.lastError }}</span>
          </div>
          <div v-if="refreshProgress.done" style="margin-top:16px;text-align:center;">
            <p style="font-size:1.1rem;font-weight:600;">刷新完成！</p>
            <p>成功 <span style="color:var(--success);font-weight:600;">{{ refreshProgress.success }}</span>，失败 <span style="color:var(--danger);font-weight:600;">{{ refreshProgress.fail }}</span></p>
            <button class="btn btn-primary" @click="refreshingAll = false; accountsStore.fetchAccounts()" style="margin-top:12px;">关闭</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Group Edit Modal -->
    <div v-if="editingGroup" class="modal-overlay" @click.self="editingGroup = null">
      <div class="modal" style="max-width: 420px;">
        <div class="modal-header">
          <h3>✏️ 编辑分组</h3>
          <button class="btn btn-icon btn-secondary" @click="editingGroup = null">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">分组名称</label>
            <input class="form-input" v-model="editingGroup.name" />
          </div>
          <div class="form-group">
            <label class="form-label">颜色</label>
            <input type="color" v-model="editingGroup.color" style="width:48px;height:36px;border:none;border-radius:6px;cursor:pointer;" />
          </div>
          <div class="form-group">
            <label class="form-label">代理 URL</label>
            <div style="display:flex;gap:6px;">
              <input class="form-input" v-model="editingGroup.proxy_url" placeholder="http://host:port 或 socks5://host:port" style="flex:1;" />
              <button v-if="editingGroup.proxy_url" class="btn btn-secondary btn-sm" @click="editingGroup.proxy_url = ''" title="清除代理" style="white-space:nowrap;">✕ 清除</button>
            </div>
            <div v-if="editingGroup.id && editingGroup.proxy_url" style="margin-top:6px;">
              <button class="btn btn-sm" :class="proxyTestResult?.ok ? 'btn-primary' : 'btn-secondary'" @click="testGroupProxy(editingGroup.id)" :disabled="proxyTesting" style="font-size:0.78rem;">
                {{ proxyTesting ? '⏳ 测试中...' : '🔍 测试代理' }}
              </button>
              <span v-if="proxyTestResult" style="font-size:0.78rem;margin-left:8px;" :style="{color: proxyTestResult.ok ? 'var(--success)' : 'var(--danger)'}">
                {{ proxyTestResult.message }}
              </span>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">描述</label>
            <input class="form-input" v-model="editingGroup.description" placeholder="分组描述 (可选)" />
          </div>
          <hr style="border-color:var(--border);margin:12px 0;" />
          <div class="form-group">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
              <label style="font-size:0.85rem;"><input type="checkbox" v-model="editingGroup.auto_sync" /> 🔄 启用自动同步</label>
            </div>
          </div>
          <div class="form-group" v-if="editingGroup.auto_sync">
            <label class="form-label">⏱ 同步设置</label>
            <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px;">
              <span style="font-size:0.85rem;white-space:nowrap;">同步间隔</span>
              <input class="form-input" type="number" v-model.number="editingGroup.sync_interval_minutes" min="1" style="width:80px;" />
              <span style="font-size:0.85rem;">分钟</span>
            </div>
            <div style="display:flex;gap:10px;align-items:center;">
              <span style="font-size:0.85rem;white-space:nowrap;">每批同步</span>
              <input class="form-input" type="number" v-model.number="editingGroup.sync_batch_size" min="1" style="width:80px;" />
              <span style="font-size:0.85rem;">个账号</span>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">🔑 Token 刷新</label>
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
              <label style="font-size:0.85rem;"><input type="checkbox" v-model="editingGroup.auto_refresh_token" /> 启用自动刷新 Token</label>
            </div>
            <div v-if="editingGroup.auto_refresh_token" style="display:flex;gap:10px;align-items:center;">
              <span style="font-size:0.85rem;white-space:nowrap;">刷新间隔</span>
              <input class="form-input" type="number" v-model.number="editingGroup.refresh_interval_hours" min="1" style="width:80px;" />
              <span style="font-size:0.85rem;">小时</span>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="editingGroup = null">取消</button>
          <button class="btn btn-primary" @click="saveEditGroup">保存</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAccountsStore } from '../stores/accounts.js'
import { useGroupsStore } from '../stores/groups.js'
import { useEmailsStore } from '../stores/emails.js'
import { useNotificationStore } from '../stores/notification.js'
import { useSearchStore } from '../stores/search.js'
import axios from 'axios'

const router = useRouter()
const accountsStore = useAccountsStore()
const groupsStore = useGroupsStore()
const emailsStore = useEmailsStore()
const notifStore = useNotificationStore()
const searchStore = useSearchStore()

const accounts = computed(() => accountsStore.accounts)
const groups = computed(() => groupsStore.groups)
const loading = computed(() => accountsStore.loading)
const emailList = computed(() => emailsStore.emails)

// Group filter
const filterGroupId = ref(null)

const filteredAccounts = computed(() => {
  if (filterGroupId.value === null) return accounts.value
  if (filterGroupId.value === 0) return accounts.value.filter(a => !a.group_id)
  return accounts.value.filter(a => a.group_id === filterGroupId.value)
})

// Batch selection
const selectedIds = ref([])
const batchMoveGroupId = ref(null)
const batchMoving = ref(false)

const allSelected = computed(() => {
  return filteredAccounts.value.length > 0 &&
    filteredAccounts.value.every(a => selectedIds.value.includes(a.id))
})

function toggleSelectAll() {
  if (allSelected.value) {
    selectedIds.value = []
  } else {
    selectedIds.value = filteredAccounts.value.map(a => a.id)
  }
}

async function handleBatchMove() {
  if (selectedIds.value.length === 0) return
  batchMoving.value = true
  try {
    await axios.patch('/api/accounts/batch-group', {
      account_ids: selectedIds.value,
      group_id: batchMoveGroupId.value,
    })
    await accountsStore.fetchAccounts()
    groupsStore.fetchGroups()
    notifStore.addToast(`已移动 ${selectedIds.value.length} 个账号`, 'success')
    selectedIds.value = []
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '批量移动失败', 'error')
  } finally {
    batchMoving.value = false
  }
}

// Email view
const emailViewAccount = ref(null)
const viewingDetail = ref(false)
const currentDetail = computed(() => emailsStore.currentEmail)

const bodyWithStyle = computed(() => {
  if (!currentDetail.value?.body_html) return ''
  return `
    <html>
      <head>
        <style>
          body {
            font-family: 'Inter', -apple-system, sans-serif;
            font-size: 14px;
            line-height: 1.65;
            color: #e0e0e0;
            background: #1a1c2e;
            padding: 20px;
            max-width: 100%;
            word-break: break-word;
            margin: 0;
          }
          img { max-width: 100%; height: auto; }
          a { color: #818cf8; }
          pre { overflow-x: auto; }
          table { border-collapse: collapse; }
          td, th { padding: 4px 8px; }
        </style>
      </head>
      <body>${currentDetail.value.body_html}</body>
    </html>
  `
})

function toggleEmailView(account) {
  if (emailViewAccount.value && emailViewAccount.value.id === account.id) {
    closeEmailModal()
  } else {
    emailViewAccount.value = account
    viewingDetail.value = false
    emailFolder.value = 'inbox'
    emailsStore.clearDetail()
    emailsStore.fetchEmails(account.id, 30, 0, 'inbox')
  }
}

function closeEmailModal() {
  emailViewAccount.value = null
  viewingDetail.value = false
  emailsStore.emails = []
  emailsStore.clearDetail()
}

function refreshEmails() {
  if (emailViewAccount.value) {
    emailsStore.fetchEmails(emailViewAccount.value.id, 30, 0, emailFolder.value)
  }
}

function openEmail(email) {
  viewingDetail.value = true
  emailsStore.fetchEmailDetail(emailViewAccount.value.id, email.id)
}

function backToList() {
  viewingDetail.value = false
  emailsStore.clearDetail()
}

function formatDetailTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Add form
const showAddModal = ref(false)
const adding = ref(false)
const form = ref({ email: '', password: '', client_id: '', refresh_token: '', group_id: null, remark: '' })

// Batch import
const showBatchModal = ref(false)
const importing = ref(false)
const batchText = ref('')
const batchResult = ref(null)
const batchGroupId = ref(null)

// Group management
const showGroupModal = ref(false)
const newGroupName = ref('')
const newGroupColor = ref('#6366f1')
const newGroupProxy = ref('')
const editingGroup = ref(null)

// Folder tabs
const emailFolder = ref('inbox')
const folders = [
  { value: 'inbox', label: '收件箱', icon: '📥' },
  { value: 'junkemail', label: '垃圾邮件', icon: '🗑️' },
  { value: 'deleteditems', label: '已删除', icon: '🗂️' },
]

function switchFolder(folder) {
  emailFolder.value = folder
  if (emailViewAccount.value) {
    viewingDetail.value = false
    emailsStore.clearDetail()
    emailsStore.fetchEmails(emailViewAccount.value.id, 30, 0, folder)
  }
}

// Settings
const showSettingsModal = ref(false)
const settingsOldPwd = ref('')
const settingsNewPwd = ref('')
const settingsApiKey = ref('')
const refreshEnabled = ref(false)
const refreshMode = ref('days')
const refreshDays = ref(30)
const refreshCron = ref('0 3 * * *')

// Token refresh
const refreshingAll = ref(false)
const refreshProgress = ref({ current: 0, total: 0, success: 0, fail: 0, done: false, lastEmail: '', lastOk: true, lastError: '' })

// Delete
const deleteTarget = ref(null)
const deleting = ref(false)

function statusText(s) {
  return { active: '正常', error: '异常', syncing: '同步中', disabled: '已禁用' }[s] || s
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatEmailTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  if (d.toDateString() === now.toDateString()) {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function filterByGroup(gid) {
  filterGroupId.value = gid
}

const syncing = ref(false)

async function refreshAll() {
  syncing.value = true
  try {
    await axios.post('/api/accounts/sync-all')
    await accountsStore.fetchAccounts()
    groupsStore.fetchGroups()
    notifStore.addToast('同步完成', 'success')
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '同步失败', 'error')
    accountsStore.fetchAccounts()
  } finally {
    syncing.value = false
  }
}

async function syncOne(id) {
  try {
    await accountsStore.syncAccount(id)
    notifStore.addToast('同步成功', 'success')
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '同步失败', 'error')
  }
}

// Device code authorization
const deviceCode = ref(null)
const deviceCodeStatus = ref('pending')
const deviceCodeError = ref('')
let deviceCodePollTimer = null
let deviceCodeAccountId = null

async function authorizeAccount(accountId) {
  try {
    const resp = await axios.post(`/api/oauth/device-start/${accountId}`)
    deviceCode.value = resp.data
    deviceCodeStatus.value = 'pending'
    deviceCodeError.value = ''
    deviceCodeAccountId = accountId
    // Start polling
    startDeviceCodePolling(accountId)
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '获取设备码失败', 'error')
  }
}

function startDeviceCodePolling(accountId) {
  stopDeviceCodePolling()
  deviceCodePollTimer = setInterval(async () => {
    try {
      const resp = await axios.post(`/api/oauth/device-poll/${accountId}`)
      if (resp.data.status === 'success') {
        deviceCodeStatus.value = 'success'
        stopDeviceCodePolling()
        notifStore.addToast('授权成功！', 'success')
        setTimeout(() => {
          deviceCode.value = null
          accountsStore.fetchAccounts()
        }, 1500)
      }
    } catch (e) {
      if (e.response?.status === 400) {
        deviceCodeStatus.value = 'error'
        deviceCodeError.value = e.response?.data?.detail || '授权失败'
        stopDeviceCodePolling()
      }
    }
  }, 5000)
}

function stopDeviceCodePolling() {
  if (deviceCodePollTimer) {
    clearInterval(deviceCodePollTimer)
    deviceCodePollTimer = null
  }
}

function cancelDeviceCode() {
  stopDeviceCodePolling()
  deviceCode.value = null
}

onUnmounted(() => {
  stopDeviceCodePolling()
})

async function changeGroup(accountId, value) {
  const groupId = value === '' ? null : parseInt(value)
  try {
    await accountsStore.updateAccountGroup(accountId, groupId)
    groupsStore.fetchGroups()
    notifStore.addToast('分组已更新', 'success')
  } catch (e) {
    notifStore.addToast('更新分组失败', 'error')
  }
}

async function handleAdd() {
  if (!form.value.email || !form.value.password) {
    notifStore.addToast('请填写邮箱和密码', 'error')
    return
  }
  adding.value = true
  try {
    await accountsStore.addAccount({ ...form.value })
    groupsStore.fetchGroups()
    notifStore.addToast('账号添加成功', 'success')
    showAddModal.value = false
    form.value = { email: '', password: '', client_id: '', refresh_token: '', group_id: null, remark: '' }
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '添加失败', 'error')
  } finally {
    adding.value = false
  }
}

async function handleBatchImport() {
  if (!batchText.value.trim()) {
    notifStore.addToast('请粘贴账号信息', 'error')
    return
  }
  importing.value = true
  batchResult.value = null
  try {
    const result = await accountsStore.batchImport(batchText.value, batchGroupId.value)
    batchResult.value = result
    groupsStore.fetchGroups()
    if (result.success > 0) {
      notifStore.addToast(`成功导入 ${result.success} 个账号`, 'success')
    }
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '导入失败', 'error')
  } finally {
    importing.value = false
  }
}

async function handleCreateGroup() {
  if (!newGroupName.value.trim()) return
  try {
    await groupsStore.createGroup({
      name: newGroupName.value.trim(),
      color: newGroupColor.value || null,
      proxy_url: newGroupProxy.value.trim() || null,
    })
    newGroupName.value = ''
    newGroupProxy.value = ''
    notifStore.addToast('分组创建成功', 'success')
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '创建失败', 'error')
  }
}

function editGroup(group) {
  editingGroup.value = { ...group }
}

async function saveEditGroup() {
  if (!editingGroup.value) return
  try {
    const payload = {
      name: editingGroup.value.name,
      color: editingGroup.value.color,
      description: editingGroup.value.description || null,
      auto_sync: editingGroup.value.auto_sync ?? false,
      sync_interval_minutes: editingGroup.value.sync_interval_minutes || 2,
      sync_batch_size: editingGroup.value.sync_batch_size || 1,
      auto_refresh_token: editingGroup.value.auto_refresh_token ?? true,
      refresh_interval_hours: editingGroup.value.refresh_interval_hours || 24,
    }
    // Explicitly send proxy_url: even if empty string or null, so backend can clear it
    payload.proxy_url = editingGroup.value.proxy_url?.trim() || null
    await groupsStore.updateGroup(editingGroup.value.id, payload)
    editingGroup.value = null
    proxyTestResult.value = null
    notifStore.addToast('分组已更新', 'success')
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '更新失败', 'error')
  }
}

// Proxy testing
const proxyTesting = ref(false)
const proxyTestResult = ref(null)

async function testGroupProxy(groupId) {
  proxyTesting.value = true
  proxyTestResult.value = null
  try {
    const { data } = await axios.post(`/api/groups/${groupId}/test-proxy`)
    proxyTestResult.value = data
  } catch (e) {
    proxyTestResult.value = {
      ok: false,
      message: e.response?.data?.detail || '测试请求失败',
    }
  } finally {
    proxyTesting.value = false
  }
}

async function toggleAutoSync(group) {
  try {
    await groupsStore.updateGroup(group.id, { auto_sync: !group.auto_sync })
    notifStore.addToast(
      group.auto_sync ? `已关闭「${group.name}」自动同步` : `已开启「${group.name}」自动同步`,
      'success'
    )
  } catch (e) {
    notifStore.addToast('更新失败', 'error')
  }
}

async function handleDeleteGroup(id) {
  try {
    await groupsStore.deleteGroup(id)
    accountsStore.fetchAccounts()
    notifStore.addToast('分组已删除', 'success')
    if (filterGroupId.value === id) filterGroupId.value = null
  } catch (e) {
    notifStore.addToast('删除失败', 'error')
  }
}

function confirmDelete(account) {
  deleteTarget.value = account
}

async function handleDelete() {
  deleting.value = true
  try {
    await accountsStore.deleteAccount(deleteTarget.value.id)
    groupsStore.fetchGroups()
    notifStore.addToast('账号已删除', 'success')
    deleteTarget.value = null
    // Close email panel if viewing deleted account
    if (emailViewAccount.value && emailViewAccount.value.id === deleteTarget.value?.id) {
      emailViewAccount.value = null
    }
  } catch (e) {
    notifStore.addToast('删除失败', 'error')
  } finally {
    deleting.value = false
  }
}

// Export
async function handleExport() {
  const params = new URLSearchParams()
  if (filterGroupId.value != null && filterGroupId.value !== 0) {
    params.set('group_id', filterGroupId.value)
  }
  const url = `/api/accounts/export${params.toString() ? '?' + params.toString() : ''}`
  try {
    const resp = await axios.get(url, { responseType: 'blob' })
    const blob = new Blob([resp.data], { type: 'text/plain' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'accounts_export.txt'
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '导出失败', 'error')
  }
}

async function handleExportSelected() {
  if (selectedIds.value.length === 0) return
  try {
    const resp = await axios.post('/api/accounts/export-selected', {
      account_ids: selectedIds.value,
    }, { responseType: 'blob' })
    const blob = new Blob([resp.data], { type: 'text/plain' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'accounts_export.txt'
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '导出失败', 'error')
  }
}

// Protocol detection
const batchChecking = ref(false)

function protocolIcon(val) {
  if (val === true) return '✅'
  if (val === false) return '❌'
  return '❓'
}

async function checkProtocols(account) {
  account._checking = true
  try {
    const { data } = await axios.post(`/api/accounts/${account.id}/check-protocols`)
    account.imap_enabled = data.imap_enabled
    account.pop3_enabled = data.pop3_enabled
    account.graph_enabled = data.graph_enabled
    notifStore.addToast(`${account.email} 协议检测完成`, 'success')
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '检测失败', 'error')
  } finally {
    account._checking = false
  }
}

async function handleBatchCheckProtocols() {
  if (selectedIds.value.length === 0) return
  batchChecking.value = true
  try {
    const { data } = await axios.post('/api/accounts/batch-check-protocols', {
      account_ids: selectedIds.value,
    })
    // Update local data
    for (const item of data.results) {
      const account = accounts.value.find(a => a.id === item.id)
      if (account) {
        if (item.imap_enabled !== undefined) account.imap_enabled = item.imap_enabled
        if (item.pop3_enabled !== undefined) account.pop3_enabled = item.pop3_enabled
        if (item.graph_enabled !== undefined) account.graph_enabled = item.graph_enabled
      }
    }
    const errors = data.results.filter(r => r.error)
    if (errors.length > 0) {
      notifStore.addToast(`检测完成，${errors.length} 个账号失败`, 'warning')
    } else {
      notifStore.addToast(`${data.results.length} 个账号协议检测完成`, 'success')
    }
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '批量检测失败', 'error')
  } finally {
    batchChecking.value = false
  }
}

// Search
const searchKeyword = ref('')
const searchGroupId = ref(null)
const searchAccountEmail = ref('')
function handleSearch() {
  searchStore.search(searchKeyword.value, searchGroupId.value, 1, searchAccountEmail.value)
}

function clearSearch() {
  searchKeyword.value = ''
  searchGroupId.value = null
  searchAccountEmail.value = ''
  searchStore.clearSearch()
}

function openSearchEmail(email) {
  // Find the account object to set up the email modal
  const account = accounts.value.find(a => a.id === email.account_id)
  if (!account) {
    notifStore.addToast(`找不到账号 ${email.account_email}`, 'error')
    return
  }
  // Open the email detail modal directly from local DB (no network calls)
  emailViewAccount.value = account
  viewingDetail.value = true
  emailsStore.fetchLocalEmailDetail(email.id)

  // Mark as read in local DB + update search result in-place
  if (!email.is_read) {
    email.is_read = true
    axios.patch(`/api/emails/${email.id}/mark-read`).catch(() => {})
  }
}

// Settings functions
async function loadSettings() {
  try {
    const { data } = await axios.get('/api/settings')
    settingsApiKey.value = data.gptmail_api_key || ''
    refreshEnabled.value = data.refresh_enabled === 'true'
    refreshMode.value = data.refresh_mode || 'days'
    refreshDays.value = parseInt(data.refresh_days) || 30
    refreshCron.value = data.refresh_cron || '0 3 * * *'
  } catch { /* ignore */ }
}

async function saveSettings() {
  try {
    await axios.put('/api/settings', {
      settings: [
        { key: 'gptmail_api_key', value: settingsApiKey.value },
        { key: 'refresh_enabled', value: refreshEnabled.value ? 'true' : 'false' },
        { key: 'refresh_mode', value: refreshMode.value },
        { key: 'refresh_days', value: String(refreshDays.value) },
        { key: 'refresh_cron', value: refreshCron.value },
      ]
    })
    notifStore.addToast('设置已保存', 'success')
    showSettingsModal.value = false
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '保存失败', 'error')
  }
}

async function handleChangePassword() {
  if (!settingsOldPwd.value || !settingsNewPwd.value) {
    notifStore.addToast('请填写旧密码和新密码', 'error')
    return
  }
  try {
    await axios.put('/api/settings/password', {
      old_password: settingsOldPwd.value,
      new_password: settingsNewPwd.value,
    })
    settingsOldPwd.value = ''
    settingsNewPwd.value = ''
    notifStore.addToast('密码已修改', 'success')
  } catch (e) {
    notifStore.addToast(e.response?.data?.detail || '修改失败', 'error')
  }
}

// SSE Token Refresh
function startRefreshAll() {
  refreshingAll.value = true
  refreshProgress.value = { current: 0, total: 0, success: 0, fail: 0, done: false, lastEmail: '', lastOk: true, lastError: '' }

  const token = localStorage.getItem('token')
  const evtSource = new EventSource(`/api/accounts/refresh-all?token=${token}`)

  evtSource.onmessage = (event) => {
    try {
      const d = JSON.parse(event.data)
      if (d.type === 'start') {
        refreshProgress.value.total = d.total
      } else if (d.type === 'progress') {
        refreshProgress.value.current = d.current
        refreshProgress.value.success = d.success_count
        refreshProgress.value.fail = d.fail_count
        refreshProgress.value.lastEmail = d.email
        refreshProgress.value.lastOk = d.success
        refreshProgress.value.lastError = d.error || ''
      } else if (d.type === 'done') {
        refreshProgress.value.done = true
        refreshProgress.value.current = d.total
        refreshProgress.value.success = d.success_count
        refreshProgress.value.fail = d.fail_count
        evtSource.close()
      }
    } catch { /* ignore parse errors */ }
  }

  evtSource.onerror = () => {
    refreshProgress.value.done = true
    evtSource.close()
  }
}

onMounted(() => {
  groupsStore.fetchGroups()
  loadSettings()
})
</script>

<style scoped>
.batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  margin-bottom: 16px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 10px;
  font-size: 0.9rem;
}

.row-active {
  background: rgba(99, 102, 241, 0.06) !important;
}

input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--accent);
}

.search-result-row:hover {
  background: rgba(99, 102, 241, 0.08) !important;
}
</style>

<style>
/* Email modal - unscoped so Teleport works */
.email-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  justify-content: center;
  align-items: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.email-modal {
  width: 680px;
  max-width: 92vw;
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(160deg, rgba(30, 32, 50, 0.98), rgba(22, 24, 38, 0.98));
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: 16px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.04);
  overflow: hidden;
}

.email-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(139, 92, 246, 0.08));
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.email-modal-title {
  display: flex;
  align-items: center;
  gap: 14px;
}

.email-modal-avatar {
  font-size: 1.6rem;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(99, 102, 241, 0.15);
  border-radius: 12px;
}

.email-modal-account {
  font-weight: 600;
  font-size: 0.95rem;
  color: #fff;
  letter-spacing: -0.01em;
}

.email-modal-subtitle {
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.45);
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.email-modal-unread-badge {
  display: inline-block;
  padding: 1px 8px;
  font-size: 0.72rem;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border-radius: 10px;
}

.email-modal-actions {
  display: flex;
  gap: 6px;
}

.email-modal-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}

.email-modal-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.15);
}

.email-modal-close:hover {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.email-modal-body {
  flex: 1;
  overflow-y: auto;
  min-height: 200px;
}

.email-modal-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 60px;
}

.email-modal-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px;
  color: rgba(255, 255, 255, 0.35);
  font-size: 0.9rem;
}

.email-items {
  padding: 4px 0;
}

.email-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px 24px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.email-item:last-child {
  border-bottom: none;
}

.email-item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.email-item-unread {
  background: rgba(99, 102, 241, 0.04);
}

.email-item-unread:hover {
  background: rgba(99, 102, 241, 0.08);
}

.email-item-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 24px;
  border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg, #6366f1, #8b5cf6);
}

.email-item-avatar {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  flex-shrink: 0;
  margin-top: 2px;
}

.email-item-content {
  flex: 1;
  min-width: 0;
}

.email-item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 3px;
}

.email-item-sender {
  font-size: 0.88rem;
  color: rgba(255, 255, 255, 0.85);
}

.email-item-unread .email-item-sender {
  font-weight: 600;
  color: #fff;
}

.email-item-time {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.3);
  white-space: nowrap;
  flex-shrink: 0;
  margin-left: 12px;
}

.email-item-subject {
  font-size: 0.84rem;
  color: rgba(255, 255, 255, 0.65);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}

.email-item-unread .email-item-subject {
  color: rgba(255, 255, 255, 0.9);
  font-weight: 500;
}

.email-item-preview {
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Transition animations */
.email-modal-enter-active {
  transition: opacity 0.25s ease;
}
.email-modal-enter-active .email-modal {
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.25s ease;
}
.email-modal-leave-active {
  transition: opacity 0.2s ease;
}
.email-modal-leave-active .email-modal {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.email-modal-enter-from {
  opacity: 0;
}
.email-modal-enter-from .email-modal {
  transform: scale(0.92) translateY(20px);
  opacity: 0;
}
.email-modal-leave-to {
  opacity: 0;
}
.email-modal-leave-to .email-modal {
  transform: scale(0.95) translateY(10px);
  opacity: 0;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.spin-icon {
  display: inline-block;
  animation: spin 1s linear infinite;
}

/* Detail mode - wider modal */
.email-modal-detail {
  width: 800px;
  max-height: 88vh;
}

.email-modal-back {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  font-size: 1.1rem;
  transition: all 0.2s;
  margin-right: 4px;
}

.email-modal-back:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.15);
}

.email-detail-view {
  display: flex;
  flex-direction: column;
}

.email-detail-meta {
  padding: 16px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
}

.email-detail-meta-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 4px 0;
  font-size: 0.84rem;
  color: rgba(255, 255, 255, 0.7);
}

.email-detail-label {
  flex-shrink: 0;
  width: 52px;
  color: rgba(255, 255, 255, 0.35);
  font-size: 0.78rem;
  text-align: right;
}

.email-detail-body {
  flex: 1;
  min-height: 0;
}

.email-detail-body iframe {
  width: 100%;
  height: 100%;
  min-height: 400px;
  border: none;
  background: #1a1c2e;
}
</style>
