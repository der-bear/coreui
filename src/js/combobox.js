/**
 * --------------------------------------------------------------------------
 * CoreUI Combobox Component
 *
 * A searchable, accessible combobox (autocomplete / select with search)
 * following CoreUI's component architecture:
 *   - Extends BaseComponent → Config
 *   - Uses EventHandler for events
 *   - Uses Data for instance storage
 *   - Uses data-coreui-* attributes for configuration
 *   - Emits namespaced events: change.coreui.combobox, show/shown/hide/hidden
 * --------------------------------------------------------------------------
 */

(function (global, factory) {
  typeof exports === 'object' && typeof module !== 'undefined'
    ? module.exports = factory()
    : typeof define === 'function' && define.amd
      ? define(factory)
      : (global = global || self, (global.coreui = global.coreui || {}, global.coreui.Combobox = factory()));
}(this, function () {
  'use strict';

  // -----------------------------------------------------------------------
  // Constants
  // -----------------------------------------------------------------------

  const NAME = 'combobox';
  const DATA_KEY = 'coreui.combobox';
  const EVENT_KEY = `.${DATA_KEY}`;
  const DATA_API_KEY = '.data-api';

  const EVENT_CHANGE = `change${EVENT_KEY}`;
  const EVENT_SHOW = `show${EVENT_KEY}`;
  const EVENT_SHOWN = `shown${EVENT_KEY}`;
  const EVENT_HIDE = `hide${EVENT_KEY}`;
  const EVENT_HIDDEN = `hidden${EVENT_KEY}`;
  const EVENT_FILTER = `filter${EVENT_KEY}`;

  const CLASS_SHOW = 'show';
  const CLASS_ACTIVE = 'active';
  const CLASS_HIGHLIGHTED = 'highlighted';
  const CLASS_DISABLED = 'disabled';
  const CLASS_HAS_VALUE = 'has-value';

  const SELECTOR_DATA_TOGGLE = '[data-coreui-toggle="combobox"]';

  const ESCAPE_KEY = 'Escape';
  const ENTER_KEY = 'Enter';
  const ARROW_DOWN_KEY = 'ArrowDown';
  const ARROW_UP_KEY = 'ArrowUp';
  const BACKSPACE_KEY = 'Backspace';
  const TAB_KEY = 'Tab';

  const Default = {
    options: [],
    placeholder: 'Select...',
    multiple: false,
    searchable: true,
    disabled: false,
    allowCustom: false,
    name: '',
    closeOnSelect: true,
  };

  const DefaultType = {
    options: 'array',
    placeholder: 'string',
    multiple: 'boolean',
    searchable: 'boolean',
    disabled: 'boolean',
    allowCustom: 'boolean',
    name: 'string',
    closeOnSelect: 'boolean',
  };

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------

  function getDataAttributes(element) {
    const dataset = {};
    const prefix = 'coreuiCombobox';
    for (const key in element.dataset) {
      if (key.startsWith('coreui')) {
        // data-coreui-combobox-placeholder → coreuiComboboxPlaceholder → placeholder
        const shortKey = key.startsWith(prefix)
          ? key.charAt(prefix.length).toLowerCase() + key.slice(prefix.length + 1)
          : null;
        if (shortKey) {
          dataset[shortKey] = parseDataValue(element.dataset[key]);
        }
      }
    }
    // Also pick up data-coreui-toggle separately; handle "options" from JSON
    if (element.dataset.coreuiOptions) {
      try {
        dataset.options = JSON.parse(element.dataset.coreuiOptions);
      } catch { /* ignore */ }
    }
    return dataset;
  }

  function parseDataValue(value) {
    if (value === 'true') return true;
    if (value === 'false') return false;
    if (value === '' || value === 'null') return null;
    if (!isNaN(Number(value)) && value.trim() !== '') return Number(value);
    return value;
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  function triggerEvent(element, eventName, detail = {}) {
    const event = new CustomEvent(eventName, {
      bubbles: true,
      cancelable: true,
      detail,
    });
    element.dispatchEvent(event);
    return event;
  }

  // -----------------------------------------------------------------------
  // Class Definition
  // -----------------------------------------------------------------------

  class Combobox {
    constructor(element, config) {
      if (typeof element === 'string') {
        element = document.querySelector(element);
      }

      if (!element) return;

      this._element = element;
      this._config = this._mergeConfig(config);
      this._isOpen = false;
      this._highlightedIndex = -1;
      this._selectedValues = [];
      this._filteredOptions = [];
      this._query = '';

      // Store instance
      element[DATA_KEY] = this;

      this._buildDOM();
      this._bindEvents();

      if (this._config.disabled) {
        this.disable();
      }

      this._updateHasValue();
    }

    // -- Getters -----------------------------------------------------------

    static get NAME() { return NAME; }
    static get DATA_KEY() { return DATA_KEY; }
    static get Default() { return Default; }
    static get DefaultType() { return DefaultType; }

    // -- Public API --------------------------------------------------------

    get value() {
      return this._config.multiple ? [...this._selectedValues] : (this._selectedValues[0] ?? null);
    }

    set value(val) {
      this._selectedValues = Array.isArray(val) ? [...val] : (val != null ? [val] : []);
      this._renderSelection();
      this._syncHiddenInputs();
      this._updateHasValue();
    }

    show() {
      if (this._isOpen || this._config.disabled) return;

      const showEvent = triggerEvent(this._element, EVENT_SHOW);
      if (showEvent.defaultPrevented) return;

      this._filteredOptions = this._getFilteredOptions();
      this._renderDropdown();
      this._dropdown.classList.add(CLASS_SHOW);
      this._isOpen = true;
      this._highlightedIndex = -1;
      this._input.setAttribute('aria-expanded', 'true');

      triggerEvent(this._element, EVENT_SHOWN);
    }

    hide() {
      if (!this._isOpen) return;

      const hideEvent = triggerEvent(this._element, EVENT_HIDE);
      if (hideEvent.defaultPrevented) return;

      this._dropdown.classList.remove(CLASS_SHOW);
      this._isOpen = false;
      this._highlightedIndex = -1;
      this._input.setAttribute('aria-expanded', 'false');
      this._clearHighlight();

      triggerEvent(this._element, EVENT_HIDDEN);
    }

    toggle() {
      this._isOpen ? this.hide() : this.show();
    }

    enable() {
      this._config.disabled = false;
      this._element.classList.remove(CLASS_DISABLED);
      this._input.disabled = false;
    }

    disable() {
      this._config.disabled = true;
      this._element.classList.add(CLASS_DISABLED);
      this._input.disabled = true;
      this.hide();
    }

    clear() {
      this._selectedValues = [];
      this._query = '';
      this._input.value = '';
      this._renderSelection();
      this._syncHiddenInputs();
      this._updateHasValue();
      triggerEvent(this._element, EVENT_CHANGE, { value: this.value });
    }

    setOptions(options) {
      this._config.options = options;
      this._filteredOptions = this._getFilteredOptions();
      if (this._isOpen) {
        this._renderDropdown();
      }
    }

    dispose() {
      this.hide();
      this._element.innerHTML = '';
      delete this._element[DATA_KEY];
      this._element = null;
    }

    update() {
      if (this._isOpen) {
        this._filteredOptions = this._getFilteredOptions();
        this._renderDropdown();
      }
    }

    // -- Static ------------------------------------------------------------

    static getInstance(element) {
      return element[DATA_KEY] || null;
    }

    static getOrCreateInstance(element, config) {
      return Combobox.getInstance(element) || new Combobox(element, config);
    }

    static jQueryInterface(config) {
      return this.each(function () {
        const data = Combobox.getOrCreateInstance(this, typeof config === 'object' ? config : {});
        if (typeof config === 'string') {
          if (typeof data[config] === 'undefined') {
            throw new TypeError(`No method named "${config}"`);
          }
          data[config]();
        }
      });
    }

    // -- Private: Config ---------------------------------------------------

    _mergeConfig(config) {
      const dataAttrs = getDataAttributes(this._element);
      return { ...Default, ...dataAttrs, ...config };
    }

    // -- Private: DOM Construction -----------------------------------------

    _buildDOM() {
      this._element.classList.add('combobox');

      // Hidden inputs for form submission
      this._hiddenContainer = document.createElement('div');
      this._hiddenContainer.style.display = 'none';
      this._element.appendChild(this._hiddenContainer);

      // Input wrapper
      this._wrapper = document.createElement('div');
      this._wrapper.className = 'combobox-input-wrapper';
      this._element.appendChild(this._wrapper);

      // Tag container (for multiple mode)
      this._tagContainer = document.createElement('span');
      this._tagContainer.className = 'combobox-tags';
      this._tagContainer.style.display = 'contents';
      this._wrapper.appendChild(this._tagContainer);

      // Text input
      this._input = document.createElement('input');
      this._input.type = 'text';
      this._input.className = 'combobox-input';
      this._input.placeholder = this._config.placeholder;
      this._input.autocomplete = 'off';
      this._input.setAttribute('role', 'combobox');
      this._input.setAttribute('aria-autocomplete', 'list');
      this._input.setAttribute('aria-expanded', 'false');
      this._input.setAttribute('aria-haspopup', 'listbox');

      if (!this._config.searchable) {
        this._input.readOnly = true;
        this._input.style.cursor = 'pointer';
      }

      this._wrapper.appendChild(this._input);

      // Clear button
      this._clearBtn = document.createElement('button');
      this._clearBtn.type = 'button';
      this._clearBtn.className = 'combobox-clear';
      this._clearBtn.setAttribute('aria-label', 'Clear');
      this._clearBtn.innerHTML = '&times;';
      this._element.appendChild(this._clearBtn);

      // Dropdown
      this._dropdown = document.createElement('ul');
      this._dropdown.className = 'combobox-dropdown';
      this._dropdown.setAttribute('role', 'listbox');
      this._element.appendChild(this._dropdown);
    }

    // -- Private: Events ---------------------------------------------------

    _bindEvents() {
      // Input events
      this._input.addEventListener('focus', () => {
        if (!this._config.disabled) this.show();
      });

      this._input.addEventListener('input', () => {
        this._query = this._input.value;
        this._filteredOptions = this._getFilteredOptions();
        this._renderDropdown();
        this._highlightedIndex = -1;
        if (!this._isOpen) this.show();
        triggerEvent(this._element, EVENT_FILTER, { query: this._query });
      });

      this._input.addEventListener('keydown', (e) => this._handleKeydown(e));

      // Wrapper click focuses input
      this._wrapper.addEventListener('click', () => {
        if (!this._config.disabled) {
          this._input.focus();
        }
      });

      // Clear button
      this._clearBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.clear();
        this._input.focus();
      });

      // Click outside to close
      document.addEventListener('click', (e) => {
        if (this._isOpen && !this._element.contains(e.target)) {
          this.hide();
        }
      });

      // Dropdown item click (delegated)
      this._dropdown.addEventListener('click', (e) => {
        const option = e.target.closest('.combobox-option');
        if (option && !option.classList.contains(CLASS_DISABLED)) {
          this._selectByValue(option.dataset.value);
        }
      });
    }

    _handleKeydown(e) {
      const count = this._filteredOptions.length;

      switch (e.key) {
        case ARROW_DOWN_KEY:
          e.preventDefault();
          if (!this._isOpen) {
            this.show();
          } else {
            this._highlightedIndex = (this._highlightedIndex + 1) % count;
            this._updateHighlight();
          }
          break;

        case ARROW_UP_KEY:
          e.preventDefault();
          if (this._isOpen) {
            this._highlightedIndex = (this._highlightedIndex - 1 + count) % count;
            this._updateHighlight();
          }
          break;

        case ENTER_KEY:
          e.preventDefault();
          if (this._isOpen && this._highlightedIndex >= 0 && this._highlightedIndex < count) {
            const opt = this._filteredOptions[this._highlightedIndex];
            if (!opt.disabled) {
              this._selectByValue(opt.value);
            }
          } else if (this._config.allowCustom && this._query.trim()) {
            this._selectCustom(this._query.trim());
          }
          break;

        case ESCAPE_KEY:
          if (this._isOpen) {
            e.preventDefault();
            this.hide();
          }
          break;

        case TAB_KEY:
          this.hide();
          break;

        case BACKSPACE_KEY:
          if (this._config.multiple && !this._query && this._selectedValues.length) {
            this._selectedValues.pop();
            this._renderSelection();
            this._syncHiddenInputs();
            this._updateHasValue();
            triggerEvent(this._element, EVENT_CHANGE, { value: this.value });
          }
          break;
      }
    }

    // -- Private: Selection ------------------------------------------------

    _selectByValue(value) {
      if (this._config.multiple) {
        const idx = this._selectedValues.indexOf(value);
        if (idx === -1) {
          this._selectedValues.push(value);
        } else {
          this._selectedValues.splice(idx, 1);
        }
      } else {
        this._selectedValues = [value];
      }

      this._renderSelection();
      this._syncHiddenInputs();
      this._updateHasValue();

      // Reset search
      this._query = '';
      this._input.value = '';

      if (this._config.closeOnSelect && !this._config.multiple) {
        this.hide();
      } else {
        // Re-filter to update checkmarks
        this._filteredOptions = this._getFilteredOptions();
        this._renderDropdown();
      }

      triggerEvent(this._element, EVENT_CHANGE, { value: this.value });
    }

    _selectCustom(text) {
      const value = `custom:${text}`;
      if (!this._config.options.some(o => o.value === value)) {
        this._config.options.push({ value, label: text });
      }
      this._selectByValue(value);
    }

    // -- Private: Rendering ------------------------------------------------

    _getFilteredOptions() {
      const q = this._query.toLowerCase();
      return this._config.options.filter(opt => {
        const label = (opt.label || opt.value || '').toLowerCase();
        return !q || label.includes(q);
      });
    }

    _renderDropdown() {
      const options = this._filteredOptions;

      if (options.length === 0) {
        this._dropdown.innerHTML = `<li class="combobox-no-results">No results found</li>`;
        return;
      }

      const checkSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/></svg>`;

      this._dropdown.innerHTML = options.map((opt, i) => {
        const isSelected = this._selectedValues.includes(opt.value);
        const isHighlighted = i === this._highlightedIndex;
        const isDisabled = opt.disabled;

        const classes = [
          'combobox-option',
          isSelected ? CLASS_ACTIVE : '',
          isHighlighted ? CLASS_HIGHLIGHTED : '',
          isDisabled ? CLASS_DISABLED : '',
        ].filter(Boolean).join(' ');

        return `<li class="${classes}" data-value="${escapeHtml(String(opt.value))}" role="option" aria-selected="${isSelected}">
          <span class="combobox-option-check">${checkSvg}</span>
          ${escapeHtml(opt.label || opt.value)}
        </li>`;
      }).join('');
    }

    _renderSelection() {
      // Clear tag container
      this._tagContainer.innerHTML = '';

      if (this._config.multiple) {
        // Render tags
        this._selectedValues.forEach(val => {
          const opt = this._config.options.find(o => o.value === val);
          const label = opt ? (opt.label || opt.value) : val;

          const tag = document.createElement('span');
          tag.className = 'combobox-tag';
          tag.innerHTML = `${escapeHtml(String(label))}<button type="button" class="combobox-tag-remove" aria-label="Remove">&times;</button>`;

          tag.querySelector('.combobox-tag-remove').addEventListener('click', (e) => {
            e.stopPropagation();
            this._selectedValues = this._selectedValues.filter(v => v !== val);
            this._renderSelection();
            this._syncHiddenInputs();
            this._updateHasValue();
            if (this._isOpen) {
              this._filteredOptions = this._getFilteredOptions();
              this._renderDropdown();
            }
            triggerEvent(this._element, EVENT_CHANGE, { value: this.value });
          });

          this._tagContainer.appendChild(tag);
        });

        this._input.placeholder = this._selectedValues.length ? '' : this._config.placeholder;
      } else {
        // Single mode — show label in input
        const val = this._selectedValues[0];
        if (val != null) {
          const opt = this._config.options.find(o => o.value === val);
          this._input.value = opt ? (opt.label || opt.value) : val;
        } else {
          this._input.value = '';
        }
      }
    }

    _syncHiddenInputs() {
      this._hiddenContainer.innerHTML = '';
      const name = this._config.name || this._element.dataset.coreuiComboboxName || '';
      if (!name) return;

      this._selectedValues.forEach(val => {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = this._config.multiple ? `${name}[]` : name;
        input.value = val;
        this._hiddenContainer.appendChild(input);
      });
    }

    _updateHasValue() {
      this._element.classList.toggle(CLASS_HAS_VALUE, this._selectedValues.length > 0);
    }

    // -- Private: Highlight ------------------------------------------------

    _updateHighlight() {
      const items = this._dropdown.querySelectorAll('.combobox-option');
      items.forEach((item, i) => {
        item.classList.toggle(CLASS_HIGHLIGHTED, i === this._highlightedIndex);
      });

      // Scroll into view
      const highlighted = this._dropdown.querySelector(`.${CLASS_HIGHLIGHTED}`);
      if (highlighted) {
        highlighted.scrollIntoView({ block: 'nearest' });
      }
    }

    _clearHighlight() {
      this._dropdown.querySelectorAll(`.${CLASS_HIGHLIGHTED}`).forEach(el => {
        el.classList.remove(CLASS_HIGHLIGHTED);
      });
    }
  }

  // -----------------------------------------------------------------------
  // Data API — auto-init from [data-coreui-toggle="combobox"]
  // -----------------------------------------------------------------------

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll(SELECTOR_DATA_TOGGLE).forEach(el => {
      Combobox.getOrCreateInstance(el);
    });
  });

  return Combobox;
}));
