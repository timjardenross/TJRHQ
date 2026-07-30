/**
 * Agent Status API — /api/v1/agents/*
 *
 * Endpoints:
 * - GET /status              → All specialists status
 * - GET /:agent/workload    → Specific agent workload
 * - GET /:agent/activity    → Recent activity
 *
 * Data Source: Specialist availability and workload tracking
 * Cache TTL: 120 seconds (least dynamic)
 *
 * Note: Agent tracking system design deferred to Phase 2
 * This API provides contract and mock data for dashboard integration
 */

const express = require('express');
const router = express.Router();
const { cacheManager } = require('../cache/cache-manager');
const { asyncHandler, successResponse } = require('../middleware/error-handling');

/**
 * Agent directory and roles
 * ASSUMPTION: These agents are available and traceable via some system
 * (e.g., Slack status, calendar availability, task assignment)
 * Phase 2 will define the actual data source
 */
const AGENTS_DIRECTORY = {
  'chief-engineer': {
    name: 'Chief Engineer',
    role: 'Engineering Specialist',
    contact: 'chief-engineer@starfleet.local',
    availability: true
  },
  'coder-agent': {
    name: 'Coder Agent',
    role: 'Development Specialist',
    contact: 'coder@starfleet.local',
    availability: true
  },
  'risk-officer': {
    name: 'Risk Officer',
    role: 'Risk Management Specialist',
    contact: 'risk@starfleet.local',
    availability: true
  },
  'knowledge-officer': {
    name: 'Knowledge Officer',
    role: 'Knowledge Management',
    contact: 'knowledge@starfleet.local',
    availability: true
  },
  'mission-scribe': {
    name: 'Mission Scribe',
    role: 'Mission Tracking & Documentation',
    contact: 'scribe@starfleet.local',
    availability: true
  }
};

/**
 * GET /api/v1/agents/status
 * Returns status of all agents/specialists
 */
router.get('/status', asyncHandler(async (req, res) => {
  const cacheKey = 'agents:status';
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    const response = successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey: cacheKey
    });
    return res.json(response);
  }

  const statusData = {
    status: 'operational',
    timestamp: new Date().toISOString(),
    agents: [
      {
        name: 'Chief Engineer',
        role: 'Engineering Specialist',
        status: 'ACTIVE',
        missions: 3,
        availability: 'FULL',
        lastActivity: new Date(Date.now() - 300000).toISOString(), // 5 min ago
        estimatedFree: '3 days',
        workload: 'HIGH',
        specializations: ['System Architecture', 'Backend Development', 'DevOps']
      },
      {
        name: 'Coder Agent',
        role: 'Development Specialist',
        status: 'IDLE',
        missions: 1,
        availability: 'FULL',
        lastActivity: new Date(Date.now() - 1800000).toISOString(), // 30 min ago
        estimatedFree: 'Now',
        workload: 'LOW',
        specializations: ['Frontend Development', 'Testing', 'Code Review']
      },
      {
        name: 'Risk Officer',
        role: 'Risk Management Specialist',
        status: 'ACTIVE',
        missions: 2,
        availability: 'FULL',
        lastActivity: new Date(Date.now() - 600000).toISOString(), // 10 min ago
        estimatedFree: '2 days',
        workload: 'MEDIUM',
        specializations: ['Risk Assessment', 'Compliance', 'Security']
      },
      {
        name: 'Knowledge Officer',
        role: 'Knowledge Management',
        status: 'IDLE',
        missions: 1,
        availability: 'FULL',
        lastActivity: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
        estimatedFree: 'Now',
        workload: 'LOW',
        specializations: ['Documentation', 'Knowledge Base', 'Training']
      },
      {
        name: 'Mission Scribe',
        role: 'Mission Tracking & Documentation',
        status: 'ACTIVE',
        missions: 4,
        availability: 'LIMITED',
        lastActivity: new Date(Date.now() - 120000).toISOString(), // 2 min ago
        estimatedFree: '4 days',
        workload: 'HIGH',
        specializations: ['Project Management', 'Documentation', 'Status Reporting']
      }
    ],
    summary: {
      totalAgents: 5,
      activeAgents: 3,
      idleAgents: 2,
      fullAvailability: 4,
      limitedAvailability: 1,
      totalMissionsAssigned: 11,
      teamHealthScore: 'GOOD'
    }
  };

  cacheManager.set(cacheKey, statusData, 120);
  const response = successResponse(statusData, 200, {
    source: 'fresh',
    agentCount: statusData.agents.length
  });
  res.json(response);
}));

/**
 * GET /api/v1/agents/:agent/workload
 * Returns detailed workload for a specific agent
 */
router.get('/:agent/workload', asyncHandler(async (req, res) => {
  const { agent } = req.params;
  const cacheKey = `agent:${agent}:workload`;
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    const response = successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey: cacheKey
    });
    return res.json(response);
  }

  // Find agent in directory
  const agentInfo = AGENTS_DIRECTORY[agent];
  if (!agentInfo) {
    return res.status(404).json({
      status: 'error',
      error: `Agent '${agent}' not found`,
      availableAgents: Object.keys(AGENTS_DIRECTORY)
    });
  }

  // Mock workload data for agent
  const workloadData = {
    status: 'operational',
    timestamp: new Date().toISOString(),
    agent: agentInfo.name,
    role: agentInfo.role,
    currentStatus: 'ACTIVE',
    assignedMissions: [
      {
        mission: 'MSN-0032',
        title: 'Semantic Routing Integration',
        priority: 'P0',
        tasks: 5,
        completedTasks: 4,
        estimatedRemainingHours: 8,
        daysRemaining: 1,
        progress: 85
      },
      {
        mission: 'MSN-0034',
        title: 'Number One Coordination Layer',
        priority: 'P1',
        tasks: 3,
        completedTasks: 2,
        estimatedRemainingHours: 12,
        daysRemaining: 3,
        progress: 70
      },
      {
        mission: 'MSN-0035',
        title: 'STARFLEET COMMAND CENTRE',
        priority: 'P1',
        tasks: 2,
        completedTasks: 0,
        estimatedRemainingHours: 16,
        daysRemaining: 5,
        progress: 0
      }
    ],
    capacityAnalysis: {
      totalAssignedHours: 36,
      availableHoursThisWeek: 40,
      utilizationRate: 90,
      overallocated: false,
      canAcceptMore: false
    },
    nextAvailable: new Date(Date.now() + 259200000).toISOString(), // 3 days
    recommendations: [
      'Agent at near-capacity',
      'MSN-0032 should complete first',
      'MSN-0035 can be deferred slightly if needed'
    ]
  };

  cacheManager.set(cacheKey, workloadData, 120);
  const response = successResponse(workloadData, 200, {
    source: 'fresh',
    agent: agentInfo.name
  });
  res.json(response);
}));

/**
 * GET /api/v1/agents/:agent/activity
 * Returns recent activity for a specific agent
 */
router.get('/:agent/activity', asyncHandler(async (req, res) => {
  const { agent } = req.params;
  const cacheKey = `agent:${agent}:activity`;
  const { value, isStale } = cacheManager.get(cacheKey);

  if (value) {
    const response = successResponse(value, 200, {
      source: isStale ? 'stale_cache' : 'cache',
      cacheKey: cacheKey
    });
    return res.json(response);
  }

  // Find agent in directory
  const agentInfo = AGENTS_DIRECTORY[agent];
  if (!agentInfo) {
    return res.status(404).json({
      status: 'error',
      error: `Agent '${agent}' not found`,
      availableAgents: Object.keys(AGENTS_DIRECTORY)
    });
  }

  // Mock activity data
  const activityData = {
    status: 'operational',
    timestamp: new Date().toISOString(),
    agent: agentInfo.name,
    recentActivities: [
      {
        timestamp: new Date(Date.now() - 300000).toISOString(),
        type: 'TASK_COMPLETED',
        mission: 'MSN-0032',
        description: 'Completed semantic routing test suite',
        details: 'All 25 tests passing'
      },
      {
        timestamp: new Date(Date.now() - 900000).toISOString(),
        type: 'STATUS_UPDATE',
        mission: 'MSN-0034',
        description: 'Phase 2 testing in progress',
        details: 'Integration tests running'
      },
      {
        timestamp: new Date(Date.now() - 1800000).toISOString(),
        type: 'MISSION_STARTED',
        mission: 'MSN-0035',
        description: 'Joined Phase 2 API integration work',
        details: 'Backend setup initiated'
      },
      {
        timestamp: new Date(Date.now() - 3600000).toISOString(),
        type: 'COMMUNICATION',
        mission: 'MSN-0032',
        description: 'Status update provided',
        details: 'Shared progress on semantic routing'
      },
      {
        timestamp: new Date(Date.now() - 5400000).toISOString(),
        type: 'TASK_ASSIGNED',
        mission: 'MSN-0035',
        description: 'Assigned to Phase 2 API work',
        details: 'Mission Registry API implementation'
      }
    ],
    activitySummary: {
      tasksCompletedToday: 1,
      communicationsToday: 1,
      tasksInProgress: 5,
      currentMission: 'MSN-0032'
    },
    lastStatusCheck: new Date().toISOString(),
    availability: 'AVAILABLE_SOON'
  };

  cacheManager.set(cacheKey, activityData, 120);
  const response = successResponse(activityData, 200, {
    source: 'fresh',
    agent: agentInfo.name
  });
  res.json(response);
}));

module.exports = router;
