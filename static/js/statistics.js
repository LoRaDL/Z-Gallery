// statistics.js

document.addEventListener('DOMContentLoaded', function() {
    const statisticTypeSelect = document.getElementById('statistic-type');
    const chartContainer = document.querySelector('.chart-container');
    
    // 设置默认选项为artist-weighted
    statisticTypeSelect.value = 'artist-weighted';
    
    // 页面加载时获取默认统计数据
    fetchAndRenderChart(statisticTypeSelect.value);
    
    // 监听选择框变化
    statisticTypeSelect.addEventListener('change', function() {
        fetchAndRenderChart(this.value);
    });
    
    /**
     * 获取并渲染图表
     * @param {string} type - 统计类型
     */
    function fetchAndRenderChart(type) {
        fetch(`/api/statistics/${type}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    renderHorizontalBarChart(data.data, type);
                } else {
                    console.error('Failed to fetch statistics:', data.error);
                }
            })
            .catch(error => {
                console.error('Error fetching statistics:', error);
            });
    }
    
    /**
     * 渲染横向柱状图
     * @param {Array} data - 图表数据
     * @param {string} type - 统计类型
     */
    function renderHorizontalBarChart(data, type) {
        // 清空容器
        chartContainer.innerHTML = '';
        
        // 创建图表容器
        const chart = document.createElement('div');
        chart.className = 'horizontal-bar-chart';
        
        // 找到最大值用于计算比例
        const maxValue = Math.max(...data.map(item => item.value));
        
        // 为每个数据项创建柱状图元素
        data.forEach(item => {
            const barItem = document.createElement('div');
            barItem.className = 'bar-item';
            
            const label = document.createElement('div');
            label.className = 'bar-label';
            
            // 根据统计类型决定标签是否可点击
            if (type === 'artist-works' || type === 'artist-stars' || type === 'artist-average' || type === 'artist-weighted') {
                const link = document.createElement('a');
                link.href = `${window.location.origin}/?artist=${encodeURIComponent(item.label)}`;
                link.textContent = item.label;
                label.appendChild(link);
            } else if (type === 'rating') {
                const link = document.createElement('a');
                // 修改为使用rating_filter参数进行特定分数筛选
                link.href = `${window.location.origin}/?rating_filter=${item.label}`;
                link.textContent = item.label;
                label.appendChild(link);
            } else {
                label.textContent = item.label;
            }
            
            const barContainer = document.createElement('div');
            barContainer.className = 'bar-container';
            
            const barFill = document.createElement('div');
            barFill.className = 'bar-fill';
            
            // 处理负值情况：使用绝对值计算宽度，并添加负值样式
            if (item.value < 0) {
                barFill.style.width = `${(Math.abs(item.value) / maxValue) * 100}%`;
                barFill.classList.add('negative');
            } else {
                barFill.style.width = `${(item.value / maxValue) * 100}%`;
            }
            
            const value = document.createElement('div');
            value.className = 'bar-value';
            // 保留3位小数
            value.textContent = typeof item.value === 'number' ? item.value.toFixed(3) : item.value;
            
            barContainer.appendChild(barFill);
            barItem.appendChild(label);
            barItem.appendChild(barContainer);
            barItem.appendChild(value);
            
            chart.appendChild(barItem);
        });
        
        chartContainer.appendChild(chart);
    }
});