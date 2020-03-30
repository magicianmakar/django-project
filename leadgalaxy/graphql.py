class ShopifyGraphQL(object):

    def __init__(self, store):
        self.store = store

    def result(self, query, variables=None):
        return self.store.graphql(query, variables)

    def find_products_by_title(self, title, ids_only=True):
        query = '''
            query FindProductsByTitle ($title: String){
                products(first: 72, query: $title) {
                    edges {
                        node {
                            id,
                            title
                        }
                    }
                }
            }
        '''

        result = self.result(query, {'title': title})

        products = []
        for product in [i['node'] for i in result['data']['products']['edges']]:
            if ids_only:
                products.append(product['id'].split('/').pop())
            else:
                products.append(product)

        if ids_only:
            if products:
                return ','.join(products)
            else:
                # Return a random id to show "Not found" otherwise all products will be shown
                return '123'
        else:
            return products
