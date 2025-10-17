import React, { useState } from 'react';
import ReactECharts from 'echarts-for-react';
import VisualizationControls from './VisualizationControls';
import './styles/TimeSeriesViewer.css';

const TimeSeriesViewer = ({ spec, vizId }) => {
  const [selectedTimeRange, setSelectedTimeRange] = useState(null);

  // Create a separate chart option for each series
  const createChartOption = (series) => {
    // Get anomalies that affect this specific metric
    const relevantAnomalies = (spec.data.anomalies || []).filter(anomaly => {
      return !anomaly.affected_metrics || anomaly.affected_metrics.includes(series.name);
    });

    // Calculate proper Y-axis range with some padding
    const values = series.data.map(d => d.value);
    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const padding = (maxValue - minValue) * 0.1; // 10% padding

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross',
          crossStyle: { color: '#999' }
        },
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        borderColor: '#666',
        textStyle: { color: '#fff' },
        formatter: (params) => {
          if (!params || params.length === 0) return '';
          const date = new Date(params[0].value[0]);
          const value = params[0].value[1];
          return `${date.toLocaleString()}<br/>${series.name}: <strong>${value} ${series.unit || ''}</strong>`;
        }
      },
      grid: {
        left: '60px',
        right: '40px',
        bottom: '60px',
        top: '50px',
        containLabel: false
      },
      xAxis: {
        type: 'time',
        boundaryGap: false,
        axisLabel: {
          color: '#aaa',
          fontSize: 11,
          formatter: (value) => {
            const date = new Date(value);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          }
        },
        axisLine: { lineStyle: { color: '#666' } },
        axisTick: { lineStyle: { color: '#666' } },
        splitLine: { show: false },
        name: 'Time',
        nameLocation: 'middle',
        nameGap: 35,
        nameTextStyle: { color: '#aaa', fontSize: 12 }
      },
      yAxis: {
        type: 'value',
        axisLabel: {
          color: '#aaa',
          fontSize: 11,
          formatter: (value) => {
            // Format based on unit
            if (series.unit === 'percent') {
              return `${value.toFixed(1)}%`;
            } else if (series.unit === 'milliseconds') {
              return `${value.toFixed(0)}ms`;
            } else if (series.unit === 'requests/second') {
              return `${value.toFixed(0)}`;
            }
            return value.toFixed(2);
          }
        },
        name: `${series.name}${series.unit ? ' (' + series.unit + ')' : ''}`,
        nameLocation: 'middle',
        nameGap: 50,
        nameTextStyle: { color: '#fff', fontSize: 13, fontWeight: 'bold' },
        axisLine: { lineStyle: { color: '#666' } },
        axisTick: { lineStyle: { color: '#666' } },
        splitLine: { lineStyle: { color: '#333' } },
        min: Math.floor(minValue - padding),
        max: Math.ceil(maxValue + padding)
      },
      series: [
        {
          name: series.name,
          type: 'line',
          data: series.data.map(d => [d.timestamp, d.value]),
          smooth: true,
          lineStyle: {
            width: 2,
            color: series.color || '#4488ff'
          },
          itemStyle: {
            color: series.color || '#4488ff'
          },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: `${series.color || '#4488ff'}40` },
                { offset: 1, color: `${series.color || '#4488ff'}10` }
              ]
            }
          },
          showSymbol: false,
          emphasis: { focus: 'series' },
          // Add anomaly markers
          markPoint: relevantAnomalies.length > 0 ? {
            symbol: 'pin',
            symbolSize: 50,
            data: relevantAnomalies.map(anomaly => ({
              name: anomaly.description || 'Anomaly',
              coord: [anomaly.timestamp, null],
              value: anomaly.severity === 'critical' ? '⚠' : '!',
              itemStyle: {
                color: getSeverityColor(anomaly.severity)
              },
              label: {
                show: true,
                position: 'top',
                color: '#fff',
                fontSize: 16,
                formatter: () => anomaly.severity === 'critical' ? '⚠' : '!'
              }
            }))
          } : undefined
        }
      ],
      dataZoom: [
        {
          type: 'inside',
          start: 0,
          end: 100,
          filterMode: 'filter'
        },
        {
          type: 'slider',
          start: 0,
          end: 100,
          textStyle: { color: '#aaa', fontSize: 10 },
          borderColor: '#666',
          fillerColor: 'rgba(47, 69, 84, 0.4)',
          height: 20
        }
      ],
      backgroundColor: '#1e1e1e',
      darkMode: true
    };
  };

  const onChartClick = (params) => {
    if (params.componentType === 'series') {
      console.log('Clicked data point:', params);
      setSelectedTimeRange({
        start: params.value[0] - 300000, // 5 min before
        end: params.value[0] + 300000    // 5 min after
      });
    }
  };

  return (
    <div className="timeseries-viewer">
      <div className="timeseries-header">
        <h3>{spec.title}</h3>
        <VisualizationControls vizId={vizId} spec={spec} type="timeseries" />
      </div>

      <div className="timeseries-charts">
        {spec.data.series.map((series, index) => (
          <div key={index} className="timeseries-chart-container">
            <ReactECharts
              option={createChartOption(series)}
              style={{ height: '280px', width: '100%' }}
              onEvents={{
                click: onChartClick
              }}
              theme="dark"
            />
          </div>
        ))}
      </div>

      {selectedTimeRange && (
        <div className="selected-range-info">
          Selected: {new Date(selectedTimeRange.start).toLocaleTimeString()} -
          {new Date(selectedTimeRange.end).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
};

function getSeverityColor(severity) {
  switch (severity) {
    case 'critical': return 'rgba(255, 0, 0, 0.3)';
    case 'warning': return 'rgba(255, 165, 0, 0.3)';
    case 'info': return 'rgba(0, 123, 255, 0.3)';
    default: return 'rgba(128, 128, 128, 0.3)';
  }
}

export default TimeSeriesViewer;
