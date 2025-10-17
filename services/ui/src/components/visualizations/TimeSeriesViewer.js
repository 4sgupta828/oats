import React, { useState, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import VisualizationControls from './VisualizationControls';
import './styles/TimeSeriesViewer.css';

const TimeSeriesViewer = ({ spec, vizId }) => {
  const [selectedTimeRange, setSelectedTimeRange] = useState(null);
  const [globalTimeRange, setGlobalTimeRange] = useState({ start: 0, end: 100 }); // Percentage
  const [showCorrelation, setShowCorrelation] = useState(false);
  const [correlations, setCorrelations] = useState([]);

  // Calculate correlations between metrics
  const calculateCorrelation = useMemo(() => {
    if (!spec.data.series || spec.data.series.length < 2) return [];

    const results = [];
    const series = spec.data.series;

    // Calculate correlation for each pair of metrics
    for (let i = 0; i < series.length; i++) {
      for (let j = i + 1; j < series.length; j++) {
        const seriesA = series[i];
        const seriesB = series[j];

        // Get data in the selected time range
        const startIdx = Math.floor((globalTimeRange.start / 100) * seriesA.data.length);
        const endIdx = Math.ceil((globalTimeRange.end / 100) * seriesA.data.length);

        const dataA = seriesA.data.slice(startIdx, endIdx).map(d => d.value);
        const dataB = seriesB.data.slice(startIdx, endIdx).map(d => d.value);

        // Calculate Pearson correlation coefficient
        const n = Math.min(dataA.length, dataB.length);
        if (n < 2) continue;

        const meanA = dataA.reduce((a, b) => a + b, 0) / n;
        const meanB = dataB.reduce((a, b) => a + b, 0) / n;

        let numerator = 0;
        let sumSqA = 0;
        let sumSqB = 0;

        for (let k = 0; k < n; k++) {
          const diffA = dataA[k] - meanA;
          const diffB = dataB[k] - meanB;
          numerator += diffA * diffB;
          sumSqA += diffA * diffA;
          sumSqB += diffB * diffB;
        }

        const denominator = Math.sqrt(sumSqA * sumSqB);
        const correlation = denominator === 0 ? 0 : numerator / denominator;

        results.push({
          metricA: seriesA.name,
          metricB: seriesB.name,
          correlation: correlation.toFixed(3),
          strength: Math.abs(correlation) > 0.7 ? 'Strong' : Math.abs(correlation) > 0.4 ? 'Moderate' : 'Weak',
          direction: correlation > 0 ? 'Positive' : 'Negative'
        });
      }
    }

    return results.sort((a, b) => Math.abs(parseFloat(b.correlation)) - Math.abs(parseFloat(a.correlation)));
  }, [spec.data.series, globalTimeRange]);

  // Create a separate chart option for each series
  const createChartOption = (series, syncTimeRange = true) => {
    // Get anomalies that affect this specific metric
    const relevantAnomalies = (spec.data.anomalies || []).filter(anomaly => {
      return !anomaly.affected_metrics || anomaly.affected_metrics.includes(series.name);
    });

    // Filter data based on global time range
    const startIdx = Math.floor((globalTimeRange.start / 100) * series.data.length);
    const endIdx = Math.ceil((globalTimeRange.end / 100) * series.data.length);
    const filteredData = series.data.slice(startIdx, endIdx);

    // Calculate proper Y-axis range with some padding
    const values = filteredData.map(d => d.value);
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
          data: filteredData.map(d => [d.timestamp, d.value]),
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
      dataZoom: syncTimeRange ? [
        {
          type: 'inside',
          start: 0,
          end: 100,
          filterMode: 'filter'
        }
      ] : [
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
        <div className="timeseries-controls">
          <button
            className="correlation-button"
            onClick={() => {
              setShowCorrelation(!showCorrelation);
              if (!showCorrelation) setCorrelations(calculateCorrelation);
            }}
            style={{
              padding: '8px 16px',
              backgroundColor: showCorrelation ? '#4488ff' : '#2c2c2c',
              color: '#fff',
              border: '1px solid #666',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '13px',
              marginRight: '12px'
            }}
          >
            {showCorrelation ? 'Hide' : 'Show'} Correlations
          </button>
          <VisualizationControls vizId={vizId} spec={spec} type="timeseries" />
        </div>
      </div>

      {showCorrelation && correlations.length > 0 && (
        <div className="correlation-panel">
          <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#fff' }}>
            Metric Correlations (in selected range)
          </h4>
          <div className="correlation-grid">
            {correlations.map((corr, idx) => (
              <div key={idx} className="correlation-item" style={{
                padding: '10px',
                backgroundColor: '#2c2c2c',
                borderRadius: '4px',
                borderLeft: `4px solid ${corr.direction === 'Positive' ? '#4caf50' : '#f44336'}`
              }}>
                <div style={{ fontSize: '12px', fontWeight: 'bold', marginBottom: '4px' }}>
                  {corr.metricA} ⟷ {corr.metricB}
                </div>
                <div style={{ fontSize: '11px', opacity: 0.8 }}>
                  <span style={{ color: corr.direction === 'Positive' ? '#4caf50' : '#f44336' }}>
                    {corr.direction} {corr.correlation}
                  </span>
                  {' '}({corr.strength})
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Global time range slider */}
      <div className="global-time-control">
        <label style={{ fontSize: '13px', color: '#aaa', marginBottom: '8px', display: 'block' }}>
          Time Window: {globalTimeRange.start.toFixed(0)}% - {globalTimeRange.end.toFixed(0)}%
        </label>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <input
            type="range"
            min="0"
            max="100"
            value={globalTimeRange.start}
            onChange={(e) => {
              const start = parseFloat(e.target.value);
              if (start < globalTimeRange.end - 5) {
                setGlobalTimeRange({ ...globalTimeRange, start });
              }
            }}
            style={{ flex: 1 }}
          />
          <input
            type="range"
            min="0"
            max="100"
            value={globalTimeRange.end}
            onChange={(e) => {
              const end = parseFloat(e.target.value);
              if (end > globalTimeRange.start + 5) {
                setGlobalTimeRange({ ...globalTimeRange, end });
              }
            }}
            style={{ flex: 1 }}
          />
          <button
            onClick={() => setGlobalTimeRange({ start: 0, end: 100 })}
            style={{
              padding: '6px 12px',
              backgroundColor: '#2c2c2c',
              color: '#fff',
              border: '1px solid #666',
              borderRadius: '4px',
              cursor: 'pointer',
              fontSize: '11px'
            }}
          >
            Reset
          </button>
        </div>
      </div>

      <div className="timeseries-charts">
        {spec.data.series.map((series, index) => (
          <div key={index} className="timeseries-chart-container">
            <ReactECharts
              option={createChartOption(series, true)}
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
