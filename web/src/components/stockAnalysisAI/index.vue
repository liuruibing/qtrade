<template>
  <div class="ai-analysis-container">
    <!-- 分析条件选择区域 -->
    <div class="analysis-params">
      <!-- 股票选择 -->
      <div class="param-item">
        <label class="param-label">股票选择</label>
        <!-- <el-select
          v-model="selectedStock"
          placeholder="请选择股票"
          class="param-select"
          filterable
          clearable
        >
          <el-option
            v-for="stock in stockList"
            :key="stock.code"
            :label="`${stock.name} (${stock.code})`"
            :value="stock.code"
          ></el-option>
        </el-select> -->
        <el-select-v2
          v-model="selectedStock"
          :options="stockList"
          :props="{ label: 'label', value: 'symbol' }"
          placeholder="请选择"
          filterable
        />
      </div>
      <!-- 分析按钮 -->
      <div class="param-item">
        <el-button
          type="primary"
          class="analysis-btn"
          @click="startAnalysis"
          :loading="btnLoading"
        >
          开始分析
        </el-button>
      </div>
    </div>

    <!-- 无结果提示 -->
    <div
      class="no-result"
      v-if="analysisHistory.length === 0"
    >
      <el-empty description="请选择分析条件并点击开始分析"></el-empty>
    </div>

    <!-- 分析历史记录 -->
    <div
      class="history-cards"
      v-if="analysisHistory.length > 0"
    >
      <div
        v-for="(item, index) in analysisHistory"
        :key="index"
        class="history-card"
      >
        <div class="card-header">
          <div class="stock-info">
            <span class="stock-name">{{ item.stockName }}</span>
            <span class="stock-code">{{ item.stockCode }}</span>
          </div>
          <div :class="['analysis-status', item.status]">
            {{ item.status === 'analyzing' ? '分析中...' : item.status === 'success' ? '成功' : '等待分析' }}
          </div>
        </div>
        <div class="card-content">
          <div class="content-item">
            <el-rate v-model="item.score" disabled show-score text-color="#ff9900" score-template="{value}" :colors="['#99A9BF', '#F7BA2A', '#FF9900']" size="small" />
            <el-tag type="info" size="small" v-if="item.risk">{{ item.risk }}</el-tag>
          </div>
          <div class="content-item">
            <span >{{ item.advice || "--" }}</span>
          </div>
        </div>
        <div class="card-footer">
          <div class="footer-left">
            <span class="time-info">{{ item.time }}</span>
          </div>
          <div class="footer-right" v-if="item.status === 'success'">
            <el-button
              type="primary"
              size="small"
              text
              @click.stop="showDetail(item)"
              class="btn-detail"
            >
              详情
            </el-button>
            <el-button
              type="danger"
              size="small"
              text
              @click.stop="deleteHistory(index)"
              class="btn-delete"
            >
              删除
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- AI分析抽屉 -->
    <el-drawer
      v-model="aiAnalysisDrawerVisible"
      title="AI股票分析"
      size="80%"
      :before-close="handleAnalysisDrawerClose"
    >
      <div style="padding: 20px;">
        <StockAnalysis
          v-if="aiAnalysisDrawerVisible"
          :selected-stock="analysisStockData"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script lang="ts" setup>
import { ref, watch, defineProps, onMounted } from 'vue';
import { ElMessage, ElNotification } from 'element-plus';
import StockAnalysis from '/@/views/AI/stock-analysis.vue';
import { GetBaseInfo } from '/@/views/quantitative/chanlun/api';

// 接收父组件传递的股票信息
const props = defineProps<{
	symbol?: string;
}>();

// 监听父组件传递的股票变化
watch(
	() => props.symbol,
	(newSymbol) => {
		if (newSymbol) {
			selectedStock.value = newSymbol;
		}
	}
);

// 股票列表数据（模拟）
const stockList = ref([] as any[]);

const getStockList = async () => {
	try {
		const response = await GetBaseInfo({ type: 'ts_code_list' });
		const { code, data, msg } = response;
		if (code === 2000 && data) {
			let list = data || [];
			stockList.value = list.map((item: any) => {
				return {
					...item,
					label: `${item.symbol} | ${item.name}`,
				};
			});
		}
	} catch (error) {
		ElMessage.error('获取股票列表失败');
	}
};

// 选中的值
const selectedStock = ref('');
const isAnalyzing = ref(false);
const btnLoading = ref(false);

// 分析历史记录
const analysisHistory = ref([
	{
		stockCode: 'SZ.000001',
		stockName: '平安银行',
		risk: '',
		model: '趋势预测模型',
		time: new Date().toLocaleString(),
		status: 'success', // 初始状态为分析完成
		trend: '',
		confidence: 0,
		support: '',
		resistance: '',
		score: 4.5,
    advice: '建议买入',
	},
  {
		stockCode: 'SZ.000002',
		stockName: '万科A',
		risk: '低风险',
		model: '趋势预测模型',
		time: new Date().toLocaleString(),
		status: 'success', // 初始状态为分析完成
		trend: '',
		confidence: 0,
		support: '',
		resistance: '',
		score: 3.5,
    advice: '建议观望',
	},
	{
		stockCode: 'SH.600000',
		stockName: '浦发银行',
		risk: '',
		model: '趋势预测模型',
		time: new Date().toLocaleString(),
		status: 'analyzing', // 初始状态为分析中
		trend: '',
		confidence: 0,
		support: '',
		resistance: '',
    advice: '',
	},
]);

// 详情弹窗
const aiAnalysisDrawerVisible = ref(false);
const analysisStockData = ref<any>(null);

// 设置选中的股票
const setSelectedStock = (stockCode: string, flag: boolean) => {
	selectedStock.value = stockCode;
	flag && startAnalysis();
};

// 开始分析
const startAnalysis = () => {
	// 验证选择条件
	if (!selectedStock.value) {
		ElMessage.warning('请选择股票');
		return;
	}

	// 模拟分析过程
	isAnalyzing.value = true;

	// 根据股票代码找到对应的股票对象
	const stock = stockList.value.find((s) => s.symbol === selectedStock.value);

	if (!stock) {
		return;
	}

	// 立即添加到历史记录，状态为分析中
	const newHistoryItem = {
		stockCode: stock.symbol,
		stockName: stock.name,
		risk: '日线',
		model: '趋势预测模型',
		time: new Date().toLocaleString(),
		status: 'analyzing', // 初始状态为分析中
		trend: '',
		confidence: 0,
		support: '',
		resistance: '',
	};

	// 添加到历史记录
	analysisHistory.value.unshift(newHistoryItem);
	ElNotification({
		title: '已加入分析队列！',
		message: '请稍后刷新历史分析数据，分析完成后即可查看分析结果。',
		type: 'primary',
	});
	// 模拟异步分析，5秒后返回结果
	setTimeout(() => {
		// 生成模拟分析结果
		const result = generateMockAnalysisResult();

		// 更新历史记录项
		Object.assign(newHistoryItem, {
			...result,
			status: 'success', // 分析完成，状态更新为成功
			score: Math.floor(Math.random() * 5) + 3, // 3-5随机评分
		});

		isAnalyzing.value = false;
	}, 5000);
};

// 显示详情弹窗
const showDetail = (row: any) => {
	// 判断状态是否成功
	ElMessage.closeAll();
	if (row.status !== 'success') {
		ElMessage.warning('分析未完成，请等待分析完成后查看详情');
		return;
	}
	// 转换股票数据格式以适配 StockAnalysis 组件
	analysisStockData.value = {
		symbol: row.stockCode,
		name: row.stockName,
		price: 100 + Math.random() * 200, // 模拟价格
		change: (Math.random() - 0.5) * 10, // 模拟涨跌
		changePercent: (Math.random() - 0.5) * 5, // 模拟涨跌幅
		score: row.score ? Math.round(row.score * 20) : Math.floor(Math.random() * 40) + 60, // 基于评分或随机生成
		dimensions: {
			fundamental: Math.floor(Math.random() * 40) + 60,
			technical: Math.floor(Math.random() * 40) + 60,
			sentiment: Math.floor(Math.random() * 40) + 60,
			valuation: Math.floor(Math.random() * 40) + 60,
			momentum: Math.floor(Math.random() * 40) + 60,
		},
		aiSummary: `基于AI智能分析，${row.stockName}(${row.stockCode})展现出良好的投资潜力。建议投资者重点关注公司核心竞争力和市场份额变化。`,
		signals: ['技术面突破', '机构增持', '业绩稳健'],
		risks: ['市场波动', '行业竞争', '政策风险'],
	};

	// 打开抽屉
	aiAnalysisDrawerVisible.value = true;
};

// 抽屉关闭处理
const handleAnalysisDrawerClose = () => {
	aiAnalysisDrawerVisible.value = false;
	analysisStockData.value = null;
};

// 删除历史记录
const deleteHistory = (index) => {
	analysisHistory.value.splice(index, 1);
	ElMessage.success('删除成功');
};

// 生成模拟分析结果
const generateMockAnalysisResult = () => {
	// 根据股票代码找到对应的股票对象
	const stock = stockList.value.find((s) => s.code === selectedStock.value);

	if (!stock) {
		return null;
	}

	const trends = ['上涨', '下跌', '震荡'];
	const randomTrend = trends[Math.floor(Math.random() * trends.length)];
	const confidence = Math.floor(Math.random() * 30) + 70; // 70-99%
	const support = (Math.random() * 100 + 10).toFixed(2);
	const resistance = (Math.random() * 100 + 110).toFixed(2);

	return {
		stock: stock,
		risk: '',
		model: '趋势预测模型',
		time: new Date().toLocaleString(),
		trend: randomTrend,
		confidence: confidence,
		support: support,
		resistance: resistance,
	};
};

onMounted(() => {
	getStockList();
});

defineExpose({
	setSelectedStock,
});
</script>

<style scoped>
.ai-analysis-container {
	height: 100%;
	overflow-y: auto;
}

/* 分析条件样式 */
.analysis-params {
	background-color: #f9f9f9;
	padding: 16px;
	border-radius: 8px;
	margin-bottom: 16px;
	border: 1px solid #e4e7ed;
}

.param-item {
	margin-bottom: 12px;
}

.param-item:last-child {
	margin-bottom: 0;
}

.param-label {
	display: block;
	font-size: 14px;
	font-weight: 500;
	margin-bottom: 6px;
	color: #303133;
}

.param-select {
	width: 100%;
}

.analysis-btn {
	width: 100%;
	margin-top: 4px;
}

/* 无结果样式 */
.no-result {
	text-align: center;
	background-color: #f9f9f9;
	border-radius: 8px;
	border: 1px solid #e4e7ed;
}

/* 分析历史样式 */
.history-cards {
	display: flex;
	flex-direction: column;
	gap: 12px;
	overflow-y: auto;
	height: calc(100% - 210px);
}

.history-card {
	background-color: #fff;
	border: 1px solid #e4e7ed;
	border-radius: 8px;
	padding: 12px;
	box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
	transition: all 0.3s ease;
	/* cursor: pointer; */
}

.history-card:hover {
	box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
	transform: translateY(-2px);
}

.card-header {
	display: flex;
	justify-content: space-between;
	align-items: flex-start;
	margin-bottom: 12px;
	padding-bottom: 8px;
	border-bottom: 1px solid #f0f0f0;
}

.stock-info {
	flex: 1;
	overflow: hidden;
}

.stock-name {
	font-size: 14px;
	font-weight: 600;
	color: #303133;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
	margin-bottom: 2px;
}

.stock-code {
	margin-left: 10px;
	font-size: 12px;
	color: #606266;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}

.analysis-status {
	font-size: 12px;
	padding: 2px 8px;
	border-radius: 10px;
	font-weight: 500;
}

.analysis-status.success {
	background-color: #f0f9eb;
	color: #67c23a;
}

.analysis-status.analyzing {
	background-color: #ecf5ff;
	color: #409eff;
}

.analysis-status.waiting {
	background-color: #fafafa;
	color: #909399;
}

.card-content {
	margin-bottom: 12px;
}

.content-item {
	display: flex;
	justify-content: space-between;
	margin-bottom: 6px;
}

.content-item:last-child {
	margin-bottom: 0;
}

.item-label {
	font-size: 12px;
	color: #909399;
}

.item-value {
	font-size: 12px;
	color: #606266;
	font-weight: 500;
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
	max-width: 180px;
	text-align: right;
}

.card-footer {
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 8px;
	padding-top: 8px;
	border-top: 1px solid #f0f0f0;
}

.footer-left {
	display: flex;
	align-items: center;
}

.footer-right {
	display: flex;
	gap: 8px;
}

.model-info, .confidence-info, .period-info {
	display: flex;
	align-items: center;
	margin-right: 12px;
	font-size: 12px;
}

.model-label, .confidence-label, .period-label {
	color: #909399;
	margin-right: 4px;
}

.model-value, .confidence-value, .period-value {
	color: #606266;
	font-weight: 500;
}

.trend-info {
	display: flex;
	align-items: center;
}

.time-info {
	font-size: 12px;
	color: #606266;
}

.content-item {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 6px;
}

.btn-detail {
	padding: 4px 12px;
	font-size: 12px;
}

.btn-delete {
	padding: 4px 12px;
	font-size: 12px;
}

/* 滚动条样式 */
.history-cards::-webkit-scrollbar {
	width: 4px;
}

.history-cards::-webkit-scrollbar-track {
	background: #f1f1f1;
	border-radius: 2px;
}

.history-cards::-webkit-scrollbar-thumb {
	background: #c1c1c1;
	border-radius: 2px;
}

.history-cards::-webkit-scrollbar-thumb:hover {
	background: #a8a8a8;
}

/* 详情弹窗样式 */
.detail-content {
	max-height: 500px;
	overflow-y: auto;
}

.detail-item {
	margin-bottom: 12px;
}

.detail-label {
	font-weight: 500;
	color: #303133;
	margin-right: 8px;
}

.detail-value {
	color: #606266;
}

.detail-section {
	margin-top: 20px;
	margin-bottom: 20px;
}

.detail-section h4 {
	margin: 0 0 12px 0;
	font-size: 16px;
	font-weight: 600;
	color: #303133;
}

.detail-section ul {
	margin: 0;
	padding-left: 20px;
	font-size: 14px;
	color: #606266;
}

.detail-section li {
	margin-bottom: 8px;
}

.detail-section li:last-child {
	margin-bottom: 0;
}
</style>