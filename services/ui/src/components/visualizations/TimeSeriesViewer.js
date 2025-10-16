import React, { useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import VisualizationControls from './VisualizationControls';
import './styles/TimeSeriesViewer.css';

const TimeSeriesViewer = ({ spec, vizId }) => {
  const chartRef = useRef(null);
  const [selectedTimeRange, setSelectedTimeRange] = useState(null);

  const option = {
    title: {
      text: spec.title,
      textStyle: { color: '#fff' },
      left: 'center'
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        crossStyle: { color: '#999' }
      },
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      borderColor: '#666',
      textStyle: { color: '#fff' }
    },
    legend: {
      data: spec.data.series.map(s => s.name),
      textStyle: { color: '#fff' },
      top: 30
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: 80,
      containLabel: true
    },
    xAxis: {
      type: 'time',
      boundaryGap: false,
      axisLabel: {
        color: '#fff',
        formatter: (value) => {
          const date = new Date(value);
          return date.toLocaleTimeString();
        }
      },
      axisLine: { lineStyle: { color: '#666' } }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#fff' },
      name: spec.data.yAxisLabel || 'Value',
      nameTextStyle: { color: '#fff' },
      axisLine: { lineStyle: { color: '#666' } },
      splitLine: { lineStyle: { color: '#333' } }
    },
    series: [
      ...spec.data.series.map(s => ({
        name: s.name,
        type: 'line',
        data: s.data,
        smooth: true,
        lineStyle: { width: 2 },
        showSymbol: false,
        emphasis: { focus: 'series' }
      })),
      // Add anomaly visualization
      ...(spec.data.anomalies || []).map((anomaly, idx) => ({
        name: `Anomaly ${idx + 1}`,
        type: 'line',
        markArea: {
          silent: true,
          data: [[
            { xAxis: anomaly.start, name: anomaly.reason },
            { xAxis: anomaly.end }
          ]],
          itemStyle: {
            color: getSeverityColor(anomaly.severity)
          },
          label: {
            show: true,
            position: 'top',
            color: '#fff',
            formatter: () => anomaly.reason
          }
        }
      }))
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
        textStyle: { color: '#fff' },
        borderColor: '#666',
        fillerColor: 'rgba(47, 69, 84, 0.4)'
      }
    ],
    backgroundColor: '#1e1e1e',
    darkMode: true
  };

  const onChartClick = (params) => {
    if (params.componentType === 'series') {
      console.log('Clicked data point:', params);
      // Emit event to filter logs to this timestamp
      setSelectedTimeRange({
        start: params.value[0] - 300000, // 5 min before
        end: params.value[0] + 300000    // 5 min after
      });
      // TODO: Dispatch to parent to update log viewer
    }
  };

  const onDataZoom = () => {
    // const chart = chartRef.current?.getEchartsInstance();
    // if (chart) {
    //   const option = chart.getOption();
    //   // TODO: Update other visualizations based on zoom
    // }
  };

  return (
    <div className="timeseries-viewer">
      <div className="timeseries-header">
        <VisualizationControls vizId={vizId} spec={spec} type="timeseries" />
      </div>
      <ReactECharts
        ref={chartRef}
        option={option}
        style={{ height: '500px', width: '100%' }}
        onEvents={{
          click: onChartClick,
          dataZoom: onDataZoom
        }}
        theme="dark"
      />
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
