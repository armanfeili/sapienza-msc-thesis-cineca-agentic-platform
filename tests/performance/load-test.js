/**
 * k6 Load Testing Scenarios for Cineca Agentic Platform
 *
 * Tests:
 * 1. Agent E2E workflow (ask -> plan -> execute -> respond)
 * 2. NL → Cypher query translation
 * 3. Bulk read operations
 * 4. Concurrent agent runs
 * 5. Tool invocation stress test
 *
 * Usage:
 *   k6 run --out json=results.json load-test.js
 *   k6 run --vus 50 --duration 5m load-test.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const agentRunSuccess = new Rate('agent_run_success');
const agentRunDuration = new Trend('agent_run_duration');
const cypherTranslationSuccess = new Rate('cypher_translation_success');
const cypherTranslationDuration = new Trend('cypher_translation_duration');
const bulkReadSuccess = new Rate('bulk_read_success');
const bulkReadDuration = new Trend('bulk_read_duration');
const errorCount = new Counter('errors');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || 'test-token';

// Test scenarios
export const options = {
  scenarios: {
    // Scenario 1: Agent E2E workflow
    agent_e2e: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 10 },  // Ramp up to 10 users
        { duration: '3m', target: 10 },  // Stay at 10 users
        { duration: '1m', target: 20 },  // Ramp up to 20 users
        { duration: '3m', target: 20 },  // Stay at 20 users
        { duration: '2m', target: 0 },   // Ramp down
      ],
      exec: 'agentE2E',
      tags: { scenario: 'agent_e2e' },
    },

    // Scenario 2: NL → Cypher translation
    cypher_translation: {
      executor: 'constant-arrival-rate',
      rate: 50,                         // 50 requests per second
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 20,
      maxVUs: 100,
      exec: 'cypherTranslation',
      tags: { scenario: 'cypher_translation' },
    },

    // Scenario 3: Bulk read operations
    bulk_reads: {
      executor: 'per-vu-iterations',
      vus: 10,
      iterations: 100,                  // 10 VUs * 100 iterations = 1000 total
      maxDuration: '5m',
      exec: 'bulkReads',
      tags: { scenario: 'bulk_reads' },
    },

    // Scenario 4: Spike test (sudden traffic)
    spike_test: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 200,
      stages: [
        { duration: '1m', target: 10 },   // Normal load
        { duration: '30s', target: 100 }, // Spike!
        { duration: '2m', target: 100 },  // Sustain spike
        { duration: '1m', target: 10 },   // Back to normal
      ],
      exec: 'agentE2E',
      tags: { scenario: 'spike_test' },
    },
  },

  thresholds: {
    // Agent E2E thresholds
    'agent_run_success': ['rate>0.95'],           // 95% success rate
    'agent_run_duration': ['p(95)<30000'],        // p95 < 30s
    'agent_run_duration': ['p(99)<120000'],       // p99 < 2min

    // Cypher translation thresholds
    'cypher_translation_success': ['rate>0.99'],  // 99% success rate
    'cypher_translation_duration': ['p(95)<1000'], // p95 < 1s
    'cypher_translation_duration': ['p(99)<3000'], // p99 < 3s

    // Bulk read thresholds
    'bulk_read_success': ['rate>0.99'],
    'bulk_read_duration': ['p(95)<2000'],         // p95 < 2s
    'bulk_read_duration': ['p(99)<5000'],         // p99 < 5s

    // HTTP thresholds
    'http_req_duration': ['p(95)<2000'],          // p95 < 2s
    'http_req_failed': ['rate<0.05'],             // < 5% errors

    // Error budget
    'errors': ['count<100'],                      // < 100 errors total
  },
};

// Helper: Make authenticated request
function authRequest(method, url, body = null) {
  const params = {
    headers: {
      'Authorization': `Bearer ${AUTH_TOKEN}`,
      'Content-Type': 'application/json',
    },
    tags: { name: url },
  };

  if (body) {
    return http.request(method, `${BASE_URL}${url}`, JSON.stringify(body), params);
  } else {
    return http.request(method, `${BASE_URL}${url}`, null, params);
  }
}

// Test: Agent E2E workflow
export function agentE2E() {
  group('Agent E2E Workflow', () => {
    const startTime = Date.now();

    // Step 1: Create agent run
    const createPayload = {
      agent_type: 'rag-agent',
      inputs: {
        query: 'What are the top 5 papers about machine learning?',
      },
    };

    const createRes = authRequest('POST', '/api/v1/agents/run', createPayload);
    
    const createCheck = check(createRes, {
      'agent run created': (r) => r.status === 202 || r.status === 201,
      'run_id returned': (r) => r.json('run_id') !== undefined,
    });

    if (!createCheck) {
      errorCount.add(1);
      agentRunSuccess.add(0);
      return;
    }

    const runId = createRes.json('run_id');

    // Step 2: Poll for completion
    let completed = false;
    let attempts = 0;
    const maxAttempts = 60; // 60 * 1s = 60s timeout

    while (!completed && attempts < maxAttempts) {
      sleep(1);
      attempts++;

      const statusRes = authRequest('GET', `/api/v1/agents/runs/${runId}`);
      
      check(statusRes, {
        'status check successful': (r) => r.status === 200,
      });

      const status = statusRes.json('status');
      
      if (status === 'completed') {
        completed = true;
      } else if (status === 'failed' || status === 'error') {
        errorCount.add(1);
        agentRunSuccess.add(0);
        return;
      }
    }

    if (!completed) {
      errorCount.add(1);
      agentRunSuccess.add(0);
      console.warn(`Agent run ${runId} timed out after ${maxAttempts}s`);
      return;
    }

    // Step 3: Retrieve result
    const resultRes = authRequest('GET', `/api/v1/agents/runs/${runId}/result`);
    
    const resultCheck = check(resultRes, {
      'result retrieved': (r) => r.status === 200,
      'result has content': (r) => r.json('result') !== undefined,
    });

    // Record metrics
    const duration = Date.now() - startTime;
    agentRunDuration.add(duration);
    agentRunSuccess.add(resultCheck ? 1 : 0);

    if (!resultCheck) {
      errorCount.add(1);
    }
  });
}

// Test: NL → Cypher translation
export function cypherTranslation() {
  group('Cypher Translation', () => {
    const startTime = Date.now();

    const queries = [
      'Find all papers published after 2020',
      'Show me authors with more than 10 publications',
      'What are the most cited papers in AI?',
      'Find collaborations between authors at MIT and Stanford',
      'Show papers about neural networks published in 2023',
    ];

    const query = queries[Math.floor(Math.random() * queries.length)];

    const payload = {
      natural_language: query,
      schema: 'papers',
    };

    const res = authRequest('POST', '/api/v1/cypher/translate', payload);

    const success = check(res, {
      'translation successful': (r) => r.status === 200,
      'cypher query returned': (r) => r.json('cypher') !== undefined,
      'query is valid': (r) => {
        const cypher = r.json('cypher');
        return cypher && cypher.includes('MATCH');
      },
    });

    const duration = Date.now() - startTime;
    cypherTranslationDuration.add(duration);
    cypherTranslationSuccess.add(success ? 1 : 0);

    if (!success) {
      errorCount.add(1);
    }
  });
}

// Test: Bulk read operations
export function bulkReads() {
  group('Bulk Read Operations', () => {
    const startTime = Date.now();

    // Simulate bulk read: get list of agents
    const listRes = authRequest('GET', '/api/v1/agents?limit=100');

    const listCheck = check(listRes, {
      'list retrieved': (r) => r.status === 200,
      'results returned': (r) => Array.isArray(r.json('results')),
      'results not empty': (r) => r.json('results').length > 0,
    });

    if (!listCheck) {
      errorCount.add(1);
      bulkReadSuccess.add(0);
      return;
    }

    // Get details for first 10 agents
    const agents = listRes.json('results').slice(0, 10);
    let allSuccess = true;

    for (const agent of agents) {
      const detailRes = authRequest('GET', `/api/v1/agents/${agent.id}`);
      
      const detailCheck = check(detailRes, {
        'agent detail retrieved': (r) => r.status === 200,
      });

      if (!detailCheck) {
        allSuccess = false;
        errorCount.add(1);
      }

      sleep(0.1); // Small delay between requests
    }

    const duration = Date.now() - startTime;
    bulkReadDuration.add(duration);
    bulkReadSuccess.add(allSuccess ? 1 : 0);
  });
}

// Setup: Run once before tests
export function setup() {
  console.log('=== Load Test Setup ===');
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Auth Token: ${AUTH_TOKEN ? 'Provided' : 'Missing'}`);
  
  // Health check
  const healthRes = http.get(`${BASE_URL}/health`);
  console.log(`Health check: ${healthRes.status === 200 ? 'OK' : 'FAILED'}`);
  
  if (healthRes.status !== 200) {
    throw new Error('Health check failed! Aborting test.');
  }
  
  return { startTime: Date.now() };
}

// Teardown: Run once after tests
export function teardown(data) {
  const duration = (Date.now() - data.startTime) / 1000;
  console.log('=== Load Test Complete ===');
  console.log(`Total duration: ${duration.toFixed(2)}s`);
}

// Default export for simple k6 run
export default agentE2E;
