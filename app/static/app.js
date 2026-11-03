(() => {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
  const state = {
    data: null,
    sim: null,
    seq: 0,
    abort: null,
    timer: null,
  };
  const charts = new WeakMap();
  let uid = 0;

  const fmt = (value) => nf.format(value);
  const fmtTick = (value) => {
    if (value >= 1000) {
      const thousands = value / 1000;
      return `${Number.isInteger(thousands) ? thousands : thousands.toFixed(1)}k`;
    }
    return fmt(value);
  };
  const pct = (value) => `${nf1.format(value)}%`;
  const hourLabel = (hour) => `${String(hour).padStart(2, "0")}:00`;
  const nextHour = (hour) => `${String((hour + 1) % 24).padStart(2, "0")}:00`;
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  function setupTheme() {
    const buttons = $$("[data-theme-set]");
    const meta = document.querySelector('meta[name="theme-color"]');
    const apply = (theme) => {
      document.documentElement.dataset.theme = theme;
      try {
        localStorage.setItem("seoul-velo-theme", theme);
      } catch (error) {
        // Storage can be blocked. The current page still keeps the theme.
      }
      if (meta) meta.content = theme === "light" ? "#f5f5f1" : "#0d100f";
      buttons.forEach((button) => {
        const active = button.dataset.themeSet === theme;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
    };
    apply(document.documentElement.dataset.theme === "light" ? "light" : "dark");
    buttons.forEach((button) => {
      button.addEventListener("click", () => apply(button.dataset.themeSet));
    });
  }

  function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function svg(tag, attributes = {}, parent = null) {
    const node = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attributes)) {
      if (value !== null && value !== undefined) node.setAttribute(key, String(value));
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  function svgText(parent, x, y, content, className = "chart-axis", anchor = "start") {
    const node = svg("text", { x, y, class: className, "text-anchor": anchor }, parent);
    node.textContent = content;
    return node;
  }

  function linePath(points) {
    return points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  }

  function smoothPath(points) {
    if (points.length < 3) return linePath(points);
    let d = `M${points[0][0].toFixed(1)} ${points[0][1].toFixed(1)}`;
    for (let i = 0; i < points.length - 1; i += 1) {
      const p0 = points[i - 1] || points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] || p2;
      const c1x = p1[0] + (p2[0] - p0[0]) / 6;
      const c1y = p1[1] + (p2[1] - p0[1]) / 6;
      const c2x = p2[0] - (p3[0] - p1[0]) / 6;
      const c2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += ` C${c1x.toFixed(1)} ${c1y.toFixed(1)},${c2x.toFixed(1)} ${c2y.toFixed(1)},${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
    }
    return d;
  }

  function areaPath(points, baseline) {
    if (!points.length) return "";
    return `${smoothPath(points)} L${points[points.length - 1][0].toFixed(1)} ${baseline.toFixed(1)} L${points[0][0].toFixed(1)} ${baseline.toFixed(1)} Z`;
  }

  function niceMax(value) {
    if (!Number.isFinite(value) || value <= 0) return 1;
    const power = 10 ** Math.floor(Math.log10(value));
    const ratio = value / power;
    const step = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((item) => ratio <= item) || 10;
    return step * power;
  }

  function tickValues(max, target = 4) {
    if (!Number.isFinite(max) || max <= 0) return [0];
    const raw = max / target;
    const power = 10 ** Math.floor(Math.log10(raw));
    const ratio = raw / power;
    const step = (ratio <= 1 ? 1 : ratio <= 2 ? 2 : ratio <= 2.5 ? 2.5 : ratio <= 5 ? 5 : 10) * power;
    const values = [];
    for (let value = 0; value <= max + step * 0.001; value += step) values.push(value);
    return values;
  }

  function mountChart(container, draw) {
    const previous = charts.get(container);
    if (previous) previous.disconnect();
    let frame = 0;
    const render = () => {
      const width = Math.max(260, Math.round(container.getBoundingClientRect().width));
      container.replaceChildren(draw(width));
    };
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(render);
    });
    observer.observe(container);
    charts.set(container, observer);
    render();
  }

  function tooltipShow(event, html) {
    const tooltip = $("#tooltip");
    tooltip.innerHTML = html;
    tooltip.hidden = false;
    tooltipMove(event);
  }

  function tooltipMove(event) {
    const tooltip = $("#tooltip");
    if (tooltip.hidden) return;
    const rect = tooltip.getBoundingClientRect();
    const x = clamp(event.clientX, rect.width / 2 + 8, window.innerWidth - rect.width / 2 - 8);
    const y = clamp(event.clientY, rect.height + 14, window.innerHeight - 8);
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  }

  function tooltipHide() {
    $("#tooltip").hidden = true;
  }

  function renderKpis(data) {
    const { meta, models } = data;
    const best = models.metrics.find((row) => row.key === "negbin");
    setText("kpi-rides", `${(meta.rides / 1_000_000).toFixed(2)}M`);
    setText("kpi-hours", fmt(meta.operating_hours));
    setText("kpi-closed", `${fmt(meta.closed_hours)} closed hours excluded`);
    setText("kpi-peak", hourLabel(meta.peak_hour));
    setText("kpi-peak-sub", `${fmt(meta.peak_mean)} rides / hr on average`);
    setText("kpi-mae", nf1.format(best.mae));
    setText("kpi-mae-sub", `${fmt(models.test.hours)} hours held out`);
  }

  function drawPeakChart(data, width) {
    const workday = data.profiles.weekday;
    const weekend = data.profiles.weekend;
    const height = width < 560 ? 300 : 380;
    const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Average demand by hour, workday versus weekend" });
    const margin = { top: 20, right: 16, bottom: 34, left: width < 480 ? 42 : 48 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    const yMax = niceMax(Math.max(...workday, ...weekend) * 1.08);
    const x = (hour) => margin.left + (hour / 23) * plotW;
    const y = (value) => margin.top + plotH - (value / yMax) * plotH;

    tickValues(yMax, 4).forEach((value) => {
      const yy = y(value);
      svg("line", { x1: margin.left, x2: width - margin.right, y1: yy, y2: yy, class: "chart-grid" }, root);
      svgText(root, margin.left - 7, yy + 3, fmtTick(value), "chart-axis", "end");
    });

    [7, 17].forEach((start) => {
      svg(
        "rect",
        {
          x: x(start),
          y: margin.top,
          width: x(start + 2) - x(start),
          height: plotH,
          class: "chart-band",
        },
        root
      );
    });

    [0, 6, 12, 18, 23].forEach((hour) => {
      svgText(root, x(hour), height - margin.bottom + 18, String(hour).padStart(2, "0"), "chart-axis", "middle");
    });

    const workdayPoints = workday.map((value, hour) => [x(hour), y(value)]);
    const weekendPoints = weekend.map((value, hour) => [x(hour), y(value)]);
    svg("path", { d: smoothPath(weekendPoints), class: "chart-line chart-line--accent" }, root);
    svg("path", { d: smoothPath(workdayPoints), class: "chart-line chart-line--ink" }, root);

    [8, 18].forEach((hour) => {
      const px = x(hour);
      const py = y(workday[hour]);
      svg("circle", { cx: px, cy: py, r: 4, class: "chart-dot chart-dot--ink" }, root);
      svgText(root, px, py - 9, `${String(hour).padStart(2, "0")}h`, "chart-annotation", "middle");
    });

    const crosshair = svg("g", { opacity: "0" }, root);
    const crossLine = svg("line", { y1: margin.top, y2: margin.top + plotH, class: "chart-crosshair" }, crosshair);
    const dotWorkday = svg("circle", { r: 4.5, class: "chart-dot chart-dot--ink" }, crosshair);
    const dotWeekend = svg("circle", { r: 4.5, class: "chart-dot" }, crosshair);
    const overlay = svg(
      "rect",
      { x: margin.left, y: margin.top, width: plotW, height: plotH, class: "chart-hover" },
      root
    );

    overlay.addEventListener("pointermove", (event) => {
      const bounds = root.getBoundingClientRect();
      const localX = ((event.clientX - bounds.left) / bounds.width) * width;
      const hour = clamp(Math.round(((localX - margin.left) / plotW) * 23), 0, 23);
      const px = x(hour);
      crossLine.setAttribute("x1", px);
      crossLine.setAttribute("x2", px);
      dotWorkday.setAttribute("cx", px);
      dotWorkday.setAttribute("cy", y(workday[hour]));
      dotWeekend.setAttribute("cx", px);
      dotWeekend.setAttribute("cy", y(weekend[hour]));
      crosshair.setAttribute("opacity", "1");
      tooltipShow(
        event,
        `<span class="tip-title">${hourLabel(hour)}</span>
         <div class="tip-row"><span>Workday</span><b>${fmt(workday[hour])}</b></div>
         <div class="tip-row"><span>Weekend</span><b>${fmt(weekend[hour])}</b></div>`
      );
    });
    overlay.addEventListener("pointerleave", () => {
      crosshair.setAttribute("opacity", "0");
      tooltipHide();
    });

    return root;
  }

  function renderPeak(data) {
    const peaks = data.peaks;
    setText("commute-share", pct(peaks.weekday_commute_share));
    setText("evening-peak", `${fmt(peaks.evening_peak)}/hr`);
    setText("holiday-drop", `\u2212${nf1.format(peaks.holiday_gap)}%`);
    const container = $("#peak-chart");
    mountChart(container, (width) => drawPeakChart(data, width));
  }

  function renderModel(data) {
    const metrics = data.models.metrics;
    const best = metrics.find((row) => row.key === "negbin");
    const poisson = metrics.find((row) => row.key === "poisson");
    setText("model-mae", nf1.format(best.mae));
    setText("model-rmse", nf1.format(best.rmse));

    const table = $("#model-table");
    table.replaceChildren(
      ...metrics.map((metric) => {
        const row = document.createElement("tr");
        row.dataset.key = metric.key;
        row.classList.toggle("is-selected", metric.key === "negbin");
        row.innerHTML = `<td>${metric.name}${metric.key === "negbin" ? '<span class="row-badge">Selected</span>' : ""}</td><td>${nf1.format(metric.mae)}</td><td>${nf1.format(metric.rmse)}</td>`;
        return row;
      })
    );

    setText("model-aic", fmt(best.aic));
    setText("model-alpha", nf2.format(best.alpha));
    setText("model-dispersion", nf1.format(data.weather.pearson_dispersion));
    setText(
      "model-note",
      `Poisson and the negative binomial share the same mean, so point errors match. The NB adds a variance term: AIC falls from ${fmt(poisson.aic)} to ${fmt(best.aic)}. Holt–Winters never sees the weather, so it misses the peaks.`
    );
  }

  function drawTempChart(data, width) {
    const curve = data.weather.temp_curve;
    const height = width < 560 ? 250 : 300;
    const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Observed and predicted demand by temperature" });
    const margin = { top: 20, right: 16, bottom: 34, left: width < 480 ? 42 : 48 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    const temps = curve.temps;
    const observed = curve.observed.rides;
    const predicted = curve.predicted;
    const xMin = temps[0];
    const xMax = temps[temps.length - 1];
    const yMax = niceMax(Math.max(...observed, ...predicted) * 1.08);
    const x = (value) => margin.left + ((value - xMin) / (xMax - xMin)) * plotW;
    const y = (value) => margin.top + plotH - (value / yMax) * plotH;
    const baseline = y(0);

    tickValues(yMax, 4).forEach((value) => {
      const yy = y(value);
      svg("line", { x1: margin.left, x2: width - margin.right, y1: yy, y2: yy, class: "chart-grid" }, root);
      svgText(root, margin.left - 7, yy + 3, fmtTick(value), "chart-axis", "end");
    });

    [-10, 0, 10, 20, 30].filter((value) => value >= xMin && value <= xMax).forEach((value) => {
      svgText(root, x(value), height - margin.bottom + 18, `${value}\u00b0`, "chart-axis", "middle");
    });

    const points = predicted.map((value, index) => [x(temps[index]), y(value)]);
    svg("path", { d: areaPath(points, baseline), class: "chart-area" }, root);
    svg("path", { d: smoothPath(points), class: "chart-line chart-line--accent" }, root);

    curve.observed.temps.forEach((temp, index) => {
      svg("circle", { cx: x(temp), cy: y(observed[index]), r: 4, class: "chart-dot chart-dot--muted" }, root);
    });

    const crosshair = svg("g", { opacity: "0" }, root);
    const crossLine = svg("line", { y1: margin.top, y2: margin.top + plotH, class: "chart-crosshair" }, crosshair);
    const dot = svg("circle", { r: 4.5, class: "chart-dot" }, crosshair);
    const overlay = svg(
      "rect",
      { x: margin.left, y: margin.top, width: plotW, height: plotH, class: "chart-hover" },
      root
    );

    overlay.addEventListener("pointermove", (event) => {
      const bounds = root.getBoundingClientRect();
      const localX = ((event.clientX - bounds.left) / bounds.width) * width;
      const value = xMin + ((localX - margin.left) / plotW) * (xMax - xMin);
      let nearest = 0;
      temps.forEach((temp, index) => {
        if (Math.abs(temp - value) < Math.abs(temps[nearest] - value)) nearest = index;
      });
      const px = x(temps[nearest]);
      crossLine.setAttribute("x1", px);
      crossLine.setAttribute("x2", px);
      dot.setAttribute("cx", px);
      dot.setAttribute("cy", y(predicted[nearest]));
      crosshair.setAttribute("opacity", "1");
      tooltipShow(
        event,
        `<span class="tip-title">${fmt(temps[nearest])}\u00b0C</span>
         <div class="tip-row"><span>Observed</span><b>${fmt(observed[nearest])}</b></div>
         <div class="tip-row"><span>Model</span><b>${fmt(predicted[nearest])}</b></div>`
      );
    });
    overlay.addEventListener("pointerleave", () => {
      crosshair.setAttribute("opacity", "0");
      tooltipHide();
    });

    return root;
  }

  function renderWeather(data) {
    const weather = data.weather;
    const curve = weather.temp_curve;
    setText("temp-peak", `Peak ${fmt(curve.peak_temp)}\u00b0C`);
    mountChart($("#temp-chart"), (width) => drawTempChart(data, width));

    const oneMm = weather.rain_curve.find((row) => row.mm === 1);
    const deviance = weather.deviance;
    const note = $("#weather-note");
    note.innerHTML = `Calendar alone explains <strong>${pct(deviance.calendar)}</strong> of deviance; weather alone <strong>${pct(deviance.weather)}</strong>, and adds <strong>${nf1.format(deviance.weather_unique)} points</strong> after calendar. At 1 mm of rain, the model expects <strong>${pct(oneMm.drop_pct)}</strong> fewer rides.`;
  }

  function simDayLabel() {
    if (state.sim.holiday) return "Public holiday";
    return state.sim.weekend ? "Weekend" : "Workday";
  }

  function simContext(hour) {
    return `${simDayLabel()} · ${hourLabel(hour)} · ${state.sim.season}`;
  }

  function drawSimChart(result, width) {
    const height = 190;
    const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Expected demand across the day" });
    const margin = { top: 14, right: 10, bottom: 28, left: width < 420 ? 38 : 42 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    const yMax = niceMax(Math.max(...result.day) * 1.1);
    const x = (hour) => margin.left + (hour / 23) * plotW;
    const y = (value) => margin.top + plotH - (value / yMax) * plotH;
    const baseline = y(0);

    tickValues(yMax, 3).forEach((value) => {
      const yy = y(value);
      svg("line", { x1: margin.left, x2: width - margin.right, y1: yy, y2: yy, class: "chart-grid" }, root);
      svgText(root, margin.left - 5, yy + 3, fmtTick(value), "chart-axis", "end");
    });

    [0, 6, 12, 18, 23].forEach((hour) => {
      svgText(root, x(hour), height - margin.bottom + 17, String(hour).padStart(2, "0"), "chart-axis", "middle");
    });

    const points = result.day.map((value, hour) => [x(hour), y(value)]);
    svg("path", { d: areaPath(points, baseline), class: "chart-area" }, root);
    svg("path", { d: smoothPath(points), class: "chart-line chart-line--accent" }, root);

    const selectedX = x(result.hour);
    svg("line", { x1: selectedX, x2: selectedX, y1: margin.top, y2: margin.top + plotH, class: "chart-crosshair" }, root);
    svg("circle", { cx: selectedX, cy: y(result.day[result.hour]), r: 4.5, class: "chart-dot" }, root);

    return root;
  }

  function renderPrediction(result) {
    setText("sim-model", result.model);
    setText("sim-value", fmt(result.prediction));
    setText("sim-context", simContext(result.hour));
    setText("sim-range", `80% interval · ${fmt(result.interval[0])}\u2013${fmt(result.interval[1])}`);
    setText("sim-note", "Typical means the same hour, dry, with seasonal median weather. Range is the 80% predictive interval.");

    const delta = $("#sim-delta");
    delta.classList.remove("is-up", "is-down");
    if (result.delta_pct > 0.5) {
      delta.classList.add("is-up");
      delta.textContent = `+${nf1.format(result.delta_pct)}% vs typical`;
    } else if (result.delta_pct < -0.5) {
      delta.classList.add("is-down");
      delta.textContent = `\u2212${nf1.format(Math.abs(result.delta_pct))}% vs typical`;
    } else {
      delta.textContent = "about typical";
    }

    mountChart($("#sim-chart"), (width) => drawSimChart(result, width));
  }

  function requestPrediction() {
    const sim = state.sim;
    const sequence = ++state.seq;
    if (state.abort) state.abort.abort();
    state.abort = new AbortController();
    const output = $("#sim-output");
    output.classList.add("is-loading");

    fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hour: sim.hour,
        season: sim.season,
        weekend: sim.weekend,
        holiday: sim.holiday,
        temperature: sim.temperature,
        humidity: state.data.simulator.seasons[sim.season].humidity,
        rainfall: sim.rainfall,
      }),
      signal: state.abort.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((result) => {
        if (sequence === state.seq) renderPrediction(result);
      })
      .catch((error) => {
        if (error.name !== "AbortError" && sequence === state.seq) {
          setText("sim-note", "The model is unavailable right now. Refresh to try again.");
        }
      })
      .finally(() => {
        if (sequence === state.seq) output.classList.remove("is-loading");
      });
  }

  function queuePrediction() {
    clearTimeout(state.timer);
    state.timer = setTimeout(requestPrediction, 100);
  }

  function syncSimControls() {
    const sim = state.sim;
    $("#sim-hour").value = String(sim.hour);
    $("#sim-temp").value = String(sim.temperature);
    $("#sim-rain").value = String(sim.rainfall);
    $("#sim-season").value = sim.season;
    $("#sim-day").value = sim.weekend ? "weekend" : "weekday";
    $("#sim-holiday").checked = sim.holiday;
    setText("sim-hour-out", hourLabel(sim.hour));
    setText("sim-temp-out", `${fmt(sim.temperature)}\u00b0C`);
    setText("sim-rain-out", `${fmt(sim.rainfall)} mm`);
    setText("sim-context", simContext(sim.hour));
    setText("sim-value", "\u2014");
    setText("sim-range", "\u2014");
  }

  function setupSimulator(data) {
    const seasons = data.simulator.seasons;
    const seasonSelect = $("#sim-season");
    seasonSelect.replaceChildren(
      ...Object.keys(seasons).map((season) => {
        const option = document.createElement("option");
        option.value = season;
        option.textContent = season;
        return option;
      })
    );

    state.sim = {
      hour: data.simulator.default.hour,
      season: data.simulator.default.season,
      weekend: data.simulator.default.weekend,
      holiday: data.simulator.default.holiday,
      temperature: data.simulator.default.temperature,
      rainfall: data.simulator.default.rainfall,
    };
    syncSimControls();

    $("#sim-hour").addEventListener("input", (event) => {
      state.sim.hour = Number(event.target.value);
      setText("sim-hour-out", hourLabel(state.sim.hour));
      setText("sim-context", simContext(state.sim.hour));
      queuePrediction();
    });

    $("#sim-temp").addEventListener("input", (event) => {
      state.sim.temperature = Number(event.target.value);
      setText("sim-temp-out", `${fmt(state.sim.temperature)}\u00b0C`);
      queuePrediction();
    });

    $("#sim-rain").addEventListener("input", (event) => {
      state.sim.rainfall = Number(event.target.value);
      setText("sim-rain-out", `${fmt(state.sim.rainfall)} mm`);
      queuePrediction();
    });

    seasonSelect.addEventListener("change", (event) => {
      state.sim.season = event.target.value;
      setText("sim-context", simContext(state.sim.hour));
      queuePrediction();
    });

    $("#sim-day").addEventListener("change", (event) => {
      state.sim.weekend = event.target.value === "weekend";
      setText("sim-context", simContext(state.sim.hour));
      queuePrediction();
    });

    $("#sim-holiday").addEventListener("change", (event) => {
      state.sim.holiday = event.target.checked;
      setText("sim-context", simContext(state.sim.hour));
      queuePrediction();
    });

    requestPrediction();
  }

  async function init() {
    setupTheme();
    try {
      const response = await fetch("/api/dashboard");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      state.data = data;
      renderKpis(data);
      renderPeak(data);
      renderModel(data);
      renderWeather(data);
      setupSimulator(data);
    } catch (error) {
      console.error(error);
      $("#error").hidden = false;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
