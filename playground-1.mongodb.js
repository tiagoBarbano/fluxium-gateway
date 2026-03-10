// MongoDB Playground
// Use Ctrl+Space inside a snippet or a string literal to trigger completions.

// The current database to use.
use('gateway');

// Create a new document in the collection.
db.getCollection('routes').insertMany([{
  _id: 'e42ab6b4-d60c-4e0e-bb8e-ddee7d6b3667',
  tenant_id: 'emp_0001_a',
  api_id: '542eb8b7-9e07-4af7-96f9-3c92e449028c',
  prefix: '/asgi/execute/fluxo_credito_v3',
  target_base: 'http://decision-service-api:8000',
  methods: [
    'POST'
  ],
  "plugins": [
    {
      "type": "validation",
      "order": 1,
      "config": {
        "allowed_methods": ["POST"],
        "required_fields": ["order_id", "customer_id"],
        "header_rules": [
          {
            "name": "x-source",
            "required": true,
            "equals": "portal"
          }
        ],
        "query_rules": []
      }
    },
    {
      "type": "transformation",
      "order": 2,
      "config": {
        "set_headers": {
          "x-origin": "gateway"
        },
        "remove_headers": ["x-debug"],
        "json_rename": {
          "customer_id": "client_id"
        },
        "json_defaults": {
          "source": "gateway",
          "event_version": "v1"
        },
        "json_remove": ["internal_notes"]
      }
    },
    {
      "type": "event_bridge",
      "order": 3,
      "config": {
        "mode": "pubsub",
        "channel": "orders.events",
        "include_headers": false,
        "event": {
          "domain": "orders",
          "event_type": "order.created"
        },
        "forward_after_publish": false,
        "response_status": 202
      }
    },
    {
      _id: 'b2ce76b5-0bda-4523-8ec1-903c9de77774',
      tenant_id: 'emp_0001_b',
      api_id: 'b2571e8c-0de8-4bb8-bbbd-4fce0e24985d',
      prefix: '/ws/01001000/json/',
      target_base: 'https://viacep.com.br/',
      methods: [
        'GET'
      ],
      plugins: [
        {
          type: 'rate_limit',
          order: NumberInt('1'),
          config: {
            limit: NumberInt('5'),
            window_seconds: NumberInt('60')
          }
        },
        {
          type: 'cache',
          order: NumberInt('2'),
          config: {
            ttl_seconds: NumberInt('60')
          }
        }
      ]
    }
  ]
}]);
