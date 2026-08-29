(() => {
  let params;
  try {
    params = parseCardData();
  } catch (error) {
    renderDataError(error);
    console.error("周报卡片数据解析失败", error);
    return;
  }

  const projects = normalizeProjects(params.projects);
  const state = {
    projects,
    activeProjectId: null,
    submitted: Boolean(params.formDisabled),
    feedbackUser: null,
    identityPromise: null,
  };

  const elements = {
    card: document.querySelector("#feedbackCard"),
    icon: document.querySelector("#cardIcon"),
    title: document.querySelector("#cardTitle"),
    reportLink: document.querySelector("#reportLink"),
    reportLinkText: document.querySelector("#reportLinkText"),
    summary: document.querySelector("#weeklySummary"),
    projectList: document.querySelector("#projectList"),
    submitButton: document.querySelector("#submitButton"),
    submitMessage: document.querySelector("#submitMessage"),
    period: document.querySelector("#reportPeriod"),
    dialog: document.querySelector("#feedbackDialog"),
    dialogForm: document.querySelector("#dialogForm"),
    dialogProjectName: document.querySelector("#dialogProjectName"),
    feedbackInput: document.querySelector("#feedbackInput"),
  };

  /**
   * @typedef {Object} WeeklyReportProject
   * @property {string} id
   * @property {string} name
   * @property {""|"满意"|"不满意"} [satisfaction]
   * @property {string[]} [reasons]
   * @property {string} [feedback]
   * @property {{value: string, text?: {zh_CN?: string}}[]} [reasonOptions]
   */

  /**
   * @typedef {Object} WeeklyReportCardData
   * @property {1} schemaVersion
   * @property {string} iconUrl
   * @property {string} title
   * @property {string} reportUrl
   * @property {string[]} summaryMarkdown
   * @property {WeeklyReportProject[]} projects
   * @property {string[]} dissatisfactionOptions
   * @property {string} reportPeriod
   * @property {string} customer
   * @property {string} week
   * @property {string} collector
   * @property {string} reportTime
   * @property {string} submissionId
   * @property {string} callbackUrl
   */

  /** @returns {WeeklyReportCardData} */
  function parseCardData() {
    const dataElement = document.querySelector("#weeklyReportCardData");
    if (!dataElement) throw new Error("缺少 weeklyReportCardData 数据块");

    let source;
    try {
      source = JSON.parse(dataElement.textContent);
    } catch (error) {
      throw new Error(`weeklyReportCardData 不是合法 JSON：${error.message}`);
    }

    return validateCardData(source);
  }

  /** @returns {WeeklyReportCardData} */
  function validateCardData(source) {
    if (!source || typeof source !== "object" || Array.isArray(source)) {
      throw new Error("卡片数据必须是 JSON 对象");
    }
    if (source.schemaVersion !== 1) throw new Error("schemaVersion 必须为 1");

    const requiredStrings = [
      "iconUrl",
      "title",
      "reportUrl",
      "reportPeriod",
      "customer",
      "week",
      "collector",
      "reportTime",
      "submissionId",
    ];
    requiredStrings.forEach((field) => {
      if (typeof source[field] !== "string" || !source[field].trim()) {
        throw new Error(`${field} 必须是非空字符串`);
      }
    });

    if (!Array.isArray(source.summaryMarkdown)) {
      throw new Error("summaryMarkdown 必须是字符串数组");
    }
    if (!source.summaryMarkdown.every((item) => typeof item === "string")) {
      throw new Error("summaryMarkdown 只能包含字符串");
    }
    if (!Array.isArray(source.dissatisfactionOptions)) {
      throw new Error("dissatisfactionOptions 必须是字符串数组");
    }
    if (!source.dissatisfactionOptions.every((item) => typeof item === "string")) {
      throw new Error("dissatisfactionOptions 只能包含字符串");
    }
    if (!Array.isArray(source.projects) || source.projects.length === 0) {
      throw new Error("projects 必须是非空数组");
    }

    const projectIds = new Set();
    source.projects.forEach((project, index) => {
      if (!project || typeof project !== "object" || Array.isArray(project)) {
        throw new Error(`projects[${index}] 必须是对象`);
      }
      if (typeof project.id !== "string" || !project.id.trim()) {
        throw new Error(`projects[${index}].id 必须是非空字符串`);
      }
      if (projectIds.has(project.id)) throw new Error(`项目 id 重复：${project.id}`);
      projectIds.add(project.id);
      if (typeof project.name !== "string" || !project.name.trim()) {
        throw new Error(`projects[${index}].name 必须是非空字符串`);
      }
      if (project.satisfaction && !["满意", "不满意"].includes(project.satisfaction)) {
        throw new Error(`projects[${index}].satisfaction 只能是满意或不满意`);
      }
      if (project.reasons !== undefined && !Array.isArray(project.reasons)) {
        throw new Error(`projects[${index}].reasons 必须是数组`);
      }
      if (
        Array.isArray(project.reasons) &&
        !project.reasons.every((reason) => typeof reason === "string")
      ) {
        throw new Error(`projects[${index}].reasons 只能包含字符串`);
      }
      if (project.feedback !== undefined && typeof project.feedback !== "string") {
        throw new Error(`projects[${index}].feedback 必须是字符串`);
      }
      if (project.reasonOptions !== undefined && !Array.isArray(project.reasonOptions)) {
        throw new Error(`projects[${index}].reasonOptions 必须是数组`);
      }
      project.reasonOptions?.forEach((option, optionIndex) => {
        if (!option || typeof option !== "object" || Array.isArray(option)) {
          throw new Error(`projects[${index}].reasonOptions[${optionIndex}] 必须是对象`);
        }
        if (typeof option.value !== "string" || !option.value.trim()) {
          throw new Error(
            `projects[${index}].reasonOptions[${optionIndex}].value 必须是非空字符串`,
          );
        }
        if (
          option.text !== undefined &&
          (!option.text || typeof option.text !== "object" || Array.isArray(option.text))
        ) {
          throw new Error(
            `projects[${index}].reasonOptions[${optionIndex}].text 必须是对象`,
          );
        }
        if (option.text?.zh_CN !== undefined && typeof option.text.zh_CN !== "string") {
          throw new Error(
            `projects[${index}].reasonOptions[${optionIndex}].text.zh_CN 必须是字符串`,
          );
        }
      });
    });

    const optionalStrings = [
      "reportLinkText",
      "callbackUrl",
    ];
    optionalStrings.forEach((field) => {
      if (source[field] !== undefined && typeof source[field] !== "string") {
        throw new Error(`${field} 必须是字符串`);
      }
    });
    if (source.formDisabled !== undefined && typeof source.formDisabled !== "boolean") {
      throw new Error("formDisabled 必须是布尔值");
    }

    if (
      source.callbackHeaders !== undefined &&
      (!source.callbackHeaders ||
        typeof source.callbackHeaders !== "object" ||
        Array.isArray(source.callbackHeaders))
    ) {
      throw new Error("callbackHeaders 必须是 JSON 对象");
    }
    if (
      source.callbackHeaders &&
      !Object.entries(source.callbackHeaders).every(
        ([key, value]) => typeof key === "string" && typeof value === "string",
      )
    ) {
      throw new Error("callbackHeaders 的键和值都必须是字符串");
    }

    return {
      reportLinkText: "查看完整周报",
      callbackUrl: "",
      callbackHeaders: {},
      formDisabled: false,
      ...source,
    };
  }

  function renderDataError(error) {
    const card = document.querySelector("#feedbackCard");
    const content = document.createElement("section");
    const title = document.createElement("h1");
    const message = document.createElement("p");
    content.className = "data-error";
    title.className = "data-error__title";
    message.className = "data-error__message";
    title.textContent = "卡片数据无法加载";
    message.textContent = error?.message || "请检查 weeklyReportCardData JSON 数据块";
    content.append(title, message);
    card.replaceChildren(content);
  }

  function safeHttpUrl(value) {
    try {
      const url = new URL(value, window.location.href);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
    } catch {
      return "#";
    }
  }

  function normalizeSummary(value) {
    if (Array.isArray(value)) return value.filter(Boolean).map(String);
    return String(value || "")
      .split(/\r?\n/)
      .map((line) => line.replace(/^\s*[-*•]\s*/, "").trim())
      .filter(Boolean);
  }

  function normalizeProjects(value) {
    return value.map((source, index) => {
      const id = String(source.id || `p${index + 1}`);
      const globalReasons = params.dissatisfactionOptions || [];
      const reasonOptions = Array.isArray(source.reasonOptions)
        ? source.reasonOptions.map((option) => ({
            value: String(option.value || ""),
            text: option.text || { zh_CN: String(option.value || "") },
          }))
        : globalReasons.map((reason) => ({ value: reason, text: { zh_CN: reason } }));
      const reasons = Array.isArray(source.reasons) ? source.reasons.map(String) : [];

      return {
        id,
        name: String(source.name || source.project || `项目 ${index + 1}`),
        satisfaction: String(source.satisfaction || ""),
        reasonOptions,
        reasons,
        feedback: String(source.feedback || ""),
      };
    });
  }

  function appendInlineMarkdown(parent, value) {
    const fragments = String(value).split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
    fragments.forEach((fragment) => {
      if (fragment.startsWith("**") && fragment.endsWith("**")) {
        parent.append(createElement("strong", "", fragment.slice(2, -2)));
      } else {
        parent.append(document.createTextNode(fragment));
      }
    });
  }

  function selectedReasonText(project) {
    const values = Array.isArray(project.reasons) ? project.reasons : [];
    if (!values.length) return "";
    return values.join("，");
  }

  function createElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function renderSummary() {
    elements.summary.replaceChildren();
    const lines = normalizeSummary(params.summaryMarkdown || params.weeklySummary);
    elements.summary.hidden = lines.length === 0;
    lines.forEach((line) => {
      const item = createElement("li");
      appendInlineMarkdown(item, line);
      elements.summary.append(item);
    });
  }

  function renderProjects() {
    elements.projectList.replaceChildren();

    state.projects.forEach((project) => {
      const row = createElement("article", "project-row");
      row.dataset.projectId = project.id;

      const main = createElement("div", "project-main");
      const name = createElement("h2", "project-name", project.name);
      const satisfaction = createElement("div", "satisfaction-options");
      satisfaction.setAttribute("role", "radiogroup");
      satisfaction.setAttribute("aria-label", `${project.name}满意度`);

      ["满意", "不满意"].forEach((value) => {
        const label = createElement("label", "satisfaction-option");
        const input = document.createElement("input");
        input.type = "radio";
        input.name = `satisfaction-${project.id}`;
        input.value = value;
        input.checked = project.satisfaction === value;
        input.disabled = state.submitted;
        input.addEventListener("change", () => {
          project.satisfaction = value;
          row.classList.remove("is-invalid");
        });
        label.append(input, createElement("span", "", value));
        satisfaction.append(label);
      });

      const feedbackButton = createElement("button", "feedback-trigger");
      feedbackButton.type = "button";
      feedbackButton.disabled = state.submitted;
      feedbackButton.setAttribute("aria-label", `填写${project.name}具体反馈`);
      const feedbackText = createElement(
        "span",
        "feedback-trigger__text",
        project.feedback || "反馈",
      );
      const feedbackIcon = createElement("span", "feedback-trigger__icon", "✎");
      feedbackIcon.setAttribute("aria-hidden", "true");
      feedbackButton.classList.toggle("has-value", Boolean(project.feedback));
      feedbackButton.append(feedbackText, feedbackIcon);
      feedbackButton.addEventListener("click", () => openFeedbackDialog(project));

      const details = createElement("details", "reason-picker");
      details.classList.toggle("has-value", Boolean(project.reasons?.length));
      details.addEventListener("toggle", () => {
        if (!details.open) return;
        elements.projectList.querySelectorAll("details[open]").forEach((other) => {
          if (other !== details) other.removeAttribute("open");
        });
      });
      const summary = createElement("summary");
      const summaryText = createElement(
        "span",
        "reason-summary-text",
        selectedReasonText(project),
      );
      const syncReasonSummaryLabel = () => {
        const selectedText = selectedReasonText(project);
        summary.setAttribute(
          "aria-label",
          selectedText ? `已选择不满意原因：${selectedText}，点击修改` : "选择不满意原因",
        );
      };
      const chevron = createElement("span", "reason-picker__chevron", "⌄");
      chevron.setAttribute("aria-hidden", "true");
      summary.append(summaryText, chevron);
      syncReasonSummaryLabel();
      summary.addEventListener("click", (event) => {
        if (state.submitted) event.preventDefault();
      });

      const reasonOptions = createElement("div", "reason-options");
      project.reasonOptions.forEach((reasonOption) => {
        const reason = reasonOption.value;
        const label = createElement("label", "reason-option");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = reason;
        checkbox.checked = Boolean(project.reasons?.includes(reason));
        checkbox.disabled = state.submitted;
        checkbox.addEventListener("change", () => {
          project.reasons ||= [];
          if (checkbox.checked) {
            if (!project.reasons.includes(reason)) project.reasons.push(reason);
          } else {
            project.reasons = project.reasons.filter((item) => item !== reason);
          }
          summaryText.textContent = selectedReasonText(project);
          syncReasonSummaryLabel();
          details.classList.toggle("has-value", project.reasons.length > 0);
        });
        label.append(checkbox, createElement("span", "", reason));
        reasonOptions.append(label);
      });

      details.append(summary, reasonOptions);
      main.append(name, satisfaction, details);
      row.append(main, feedbackButton);
      elements.projectList.append(row);
    });
  }

  function openFeedbackDialog(project) {
    if (state.submitted) return;
    state.activeProjectId = project.id;
    elements.dialogProjectName.textContent = project.name;
    elements.feedbackInput.value = project.feedback || "";
    elements.dialog.showModal();
    syncVisualViewport();
    requestAnimationFrame(() => elements.feedbackInput.focus());
  }

  function syncVisualViewport() {
    const height = window.visualViewport?.height || window.innerHeight;
    document.documentElement.style.setProperty(
      "--visual-viewport-height",
      `${Math.round(height)}px`,
    );
  }

  window.visualViewport?.addEventListener("resize", syncVisualViewport);
  window.addEventListener("resize", syncVisualViewport);

  document.addEventListener("pointerdown", (event) => {
    if (!window.matchMedia("(min-width: 621px)").matches) return;
    if (event.target.closest(".reason-picker")) return;
    elements.projectList.querySelectorAll("details[open]").forEach((details) => {
      details.removeAttribute("open");
    });
  });

  elements.dialog.addEventListener("close", () => {
    if (elements.dialog.returnValue !== "default") return;
    const project = state.projects.find((item) => item.id === state.activeProjectId);
    if (!project) return;
    project.feedback = elements.feedbackInput.value.trim();
    renderProjects();
  });

  function buildPayload(feedbackUser) {
    const projectRows = state.projects.map((project, index) => {
      const satisfactionOptions = ["满意", "不满意"].map((value) => ({
        projectId: project.id || `p${index + 1}`,
        value,
        text: value,
        checked: project.satisfaction === value,
      }));
      const selectedReasonIndexes = project.reasons
        .map((reason) => project.reasonOptions.findIndex((option) => option.value === reason))
        .filter((reasonIndex) => reasonIndex >= 0);

      return {
        id: project.id || `p${index + 1}`,
        name: project.name,
        satisfaction: project.satisfaction,
        satisfactionOptions,
        reasonOptions: project.reasonOptions,
        selectedReasonIndexes,
        feedback: project.feedback || "",
      };
    });

    return {
      action: "submit_weekly_feedback",
      title: params.title,
      reportUrl: params.reportUrl,
      customer: params.customer,
      week: params.week,
      collector: params.collector,
      reportTime: params.reportTime,
      submissionId: params.submissionId,
      feedbackUser,
      feedbackUserId: feedbackUser.userId,
      feedbackUserName: feedbackUser.name,
      projectRows,
      projectRowsJson: JSON.stringify(projectRows),
    };
  }

  function normalizeFeedbackUser(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("钉钉返回的当前用户信息无效");
    }
    const userId = String(value.uid ?? "").trim();
    if (!userId) throw new Error("钉钉返回的当前用户信息缺少 uid");
    return {
      userId,
      name: String(value.name ?? "").trim(),
      avatar: String(value.avatar ?? "").trim(),
      corpId: String(value.corpId ?? "").trim(),
    };
  }

  async function loadFeedbackUser() {
    if (!window.DingTalkIdentity?.getCurrentUserInfo) {
      throw new Error("钉钉身份组件未加载");
    }
    const environment = window.DingTalkIdentity.getEnvironment?.();
    console.info("周报反馈页钉钉环境", environment);
    const feedbackUser = normalizeFeedbackUser(
      await window.DingTalkIdentity.getCurrentUserInfo({}),
    );
    state.feedbackUser = feedbackUser;
    console.info("周报反馈页已获取当前用户", feedbackUser);
    return feedbackUser;
  }

  function getFeedbackUser() {
    if (state.feedbackUser) return Promise.resolve(state.feedbackUser);
    state.identityPromise ||= loadFeedbackUser();
    return state.identityPromise;
  }

  function validate() {
    let valid = true;
    elements.projectList.querySelectorAll(".project-row").forEach((row) => {
      const project = state.projects.find((item) => item.id === row.dataset.projectId);
      const invalid = !project?.satisfaction;
      row.classList.toggle("is-invalid", invalid);
      valid = valid && !invalid;
    });
    return valid;
  }

  function setSubmitted() {
    state.submitted = true;
    elements.card.classList.add("is-submitted");
    elements.submitButton.textContent = "已提交";
    elements.submitButton.disabled = true;
    renderProjects();
  }

  async function submitFeedback() {
    elements.submitMessage.classList.remove("is-error");
    elements.submitMessage.textContent = "";

    if (!validate()) {
      elements.submitMessage.classList.add("is-error");
      elements.submitMessage.textContent = "请先完成每个项目的满意度选择";
      elements.projectList.querySelector(".project-row.is-invalid input")?.focus();
      return;
    }

    elements.submitButton.disabled = true;
    elements.submitButton.textContent = "提交中…";

    try {
      const feedbackUser = await getFeedbackUser();
      const payload = buildPayload(feedbackUser);
      if (params.callbackUrl) {
        const response = await fetch(params.callbackUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(params.callbackHeaders || {}),
          },
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error(`提交失败（${response.status}）`);
      } else {
        window.dispatchEvent(
          new CustomEvent("weekly-report-feedback-submit", { detail: payload }),
        );
        await new Promise((resolve) => setTimeout(resolve, 240));
      }

      setSubmitted();
      elements.submitMessage.textContent = "反馈已提交，感谢您的确认";
    } catch (error) {
      elements.submitButton.disabled = false;
      elements.submitButton.textContent = "提交";
      elements.submitMessage.classList.add("is-error");
      elements.submitMessage.textContent = error?.message || "提交失败，请稍后重试";
    }
  }

  function initialize() {
    syncVisualViewport();
    elements.icon.src = params.iconUrl;
    elements.icon.alt = `${params.customer || "客户"}图标`;
    elements.title.textContent = params.title;
    document.title = params.title;
    elements.reportLink.href = safeHttpUrl(params.reportUrl);
    elements.reportLinkText.textContent = params.reportLinkText || "查看完整周报";
    elements.period.textContent = params.reportPeriod;
    elements.submitButton.textContent = "提交";
    elements.submitButton.addEventListener("click", submitFeedback);
    state.identityPromise = loadFeedbackUser();
    state.identityPromise.catch((error) => {
      console.error("周报反馈页获取当前用户失败", error);
    });
    renderSummary();
    renderProjects();
    if (state.submitted) setSubmitted();
  }

  initialize();
})();
