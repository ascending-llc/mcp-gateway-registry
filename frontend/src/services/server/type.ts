export type GET_VERSION_RESPONSE = {
  version: string;
};

export type GET_SERVERS_QUERY = {
  query?: string;
  scope?: string;
  status?: string;
  page?: string;
  per_page?: string;
};
