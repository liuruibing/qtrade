/*
 * @Description:
 * @Author:
 * @Date: 2025-11-28 10:40:50
 * @LastEditors: Please set LastEditors
 * @LastEditTime: 2025-12-11 09:25:21
 */
import { request } from '/@/utils/service';

const baseUrl = 'http://202.46.226.13:47381';
// const baseUrl = '';

// 获取基础信息
export function GetBaseInfo(query: any) {
	return request({
		url: '/api/selection/stock-base/',
		method: 'get',
		params: query,
	});
}

// 刷新
export function RefreshData() {
	return request({
		url: '/api/selection/stock-analysis/refresh/',
		method: 'post',
	});
}

// 查询-初筛
export function GetList(query: any) {
	return request({
		url: '/api/selection/stock-selection/filter/',
		method: 'post',
		data: query,
	});
}

// 查询-精筛
export function GetFineList(query: any) {
	return request({
		// url: baseUrl + "/api/selection/stock-analysis/filter/",
		url: '/api/selection/stock-selection/refined_filter/',
		method: 'post',
		data: query,
	});
}

// 回测-K线
export function GetBacktestKline(query: any) {
	return request({
		url: '/api/selection/stock-back/kline/',
		method: 'get',
		params: query,
	});
}

// 回测-MACD
export function GetBacktestMacd(query: any) {
	return request({
		url: '/api/selection/stock-back/macd/',
		method: 'get',
		params: query,
	});
}

// 
export function GetTangle(query: any) {
	return request({
		url: '/api/selection/stock-tangle/get/',
		method: 'get',
		params: query,
	});
}
